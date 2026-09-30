import mimetypes
import os
import re
from datetime import timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from campaigns.models import Batch, Channel, MessageLog, MessageTemplate


class Command(BaseCommand):
	help = "Send scheduled WhatsApp campaign messages through the Meta Cloud API"

	def handle(self, *args, **kwargs):
		access_token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
		phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
		api_version = getattr(settings, "WHATSAPP_API_VERSION", "v23.0")
		if not access_token or not phone_number_id:
			self.stdout.write(
				self.style.ERROR(
					"WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID must be configured."
				)
			)
			return

		batches = Batch.objects.filter(
			status=Batch.Status.ACTIVE,
			sequence__channel=Channel.WHATSAPP,
		).select_related("sequence")
		if not batches.exists():
			self.stdout.write(self.style.WARNING("No active WhatsApp batches found."))
			return

		for batch in batches:
			steps = list(batch.sequence.steps.select_related("template").order_by("step_number"))
			if not steps:
				self.stdout.write(self.style.WARNING(f"Batch '{batch.name}' has no sequence steps."))
				continue

			batch_leads = batch.batch_leads.select_related("lead").filter(
				replied=False,
				unsubscribed=False,
				completed=False,
			)
			for batch_lead in batch_leads:
				if not getattr(batch_lead.lead, "whatsapp_opt_in", False):
					self.stdout.write(f"Skipping lead {batch_lead.lead_id}: WhatsApp opt-in is missing.")
					continue
				if not re.fullmatch(r"\+?[1-9]\d{1,14}", batch_lead.phone):
					self.stdout.write(f"Skipping lead {batch_lead.lead_id}: phone number must be E.164 formatted.")
					continue

				step_index = batch_lead.current_step
				if step_index >= len(steps):
					batch_lead.completed = True
					batch_lead.save(update_fields=["completed"])
					continue

				step = steps[step_index]
				template = step.template
				if not self._template_is_sendable(template):
					self.stdout.write(
						self.style.WARNING(
							f"Skipping step {step.step_number} in '{batch.name}': "
							"an approved WhatsApp template is required."
						)
					)
					continue

				send_after = batch.created_at
				if step_index:
					if not batch_lead.last_email_sent_at:
						continue
					send_after = batch_lead.last_email_sent_at + timedelta(
						days=step.delay_days,
						minutes=step.delay_minutes,
					)
				if send_after > timezone.now():
					continue

				self._send_step(
					batch=batch,
					batch_lead=batch_lead,
					step=step,
					template=template,
					access_token=access_token,
					phone_number_id=phone_number_id,
					api_version=api_version,
					step_count=len(steps),
				)

	def _send_step(
		self,
		*,
		batch,
		batch_lead,
		step,
		template,
		access_token,
		phone_number_id,
		api_version,
		step_count,
	):
		to_address = re.sub(r"\D", "", batch_lead.phone)
		log_data = {
			"batch_lead": batch_lead,
			"template": template,
			"channel": Channel.WHATSAPP,
			"step_number": step.step_number,
			"to_address": to_address,
			"subject": "",
		}

		try:
		media_header = self._upload_template_media(
			template=template,
			access_token=access_token,
			phone_number_id=phone_number_id,
			api_version=api_version,
		) if template.attachment else None
			response = requests.post(
				f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
				headers={"Authorization": f"Bearer {access_token}"},
				json={
					"messaging_product": "whatsapp",
					"to": to_address,
					"type": "template",
					"template": {
						"name": template.wa_template_name,
						"language": {"code": template.wa_language or "en"},
						"components": self._template_components(
							template,
							batch_lead,
							media_header,
						),
					},
				},
				timeout=30,
			)
			response.raise_for_status()
			response_data = response.json()
			provider_message_id = response_data.get("messages", [{}])[0].get("id", "")
			if not provider_message_id:
				raise ValueError("Meta response did not include a message ID.")
			MessageLog.objects.create(
				**log_data,
				status=MessageLog.Status.SENT,
				provider_message_id=provider_message_id,
			)

			batch_lead.current_step += 1
			batch_lead.last_email_sent_at = timezone.now()
			if batch_lead.current_step >= step_count:
				batch_lead.completed = True
			batch_lead.save(
				update_fields=["current_step", "last_email_sent_at", "completed"]
			)
			self.stdout.write(self.style.SUCCESS(f"Sent WhatsApp to {to_address}, step {step.step_number}."))
		except (requests.RequestException, ValueError, IndexError, KeyError, OSError) as error:
			MessageLog.objects.create(
				**log_data,
				status=MessageLog.Status.FAILED,
				error=str(error),
			)
			self.stdout.write(self.style.ERROR(f"WhatsApp send failed for {to_address}: {error}"))

	@staticmethod
	def _template_is_sendable(template: MessageTemplate) -> bool:
		return (
			template.channel == Channel.WHATSAPP
			and bool(template.wa_template_name)
			and template.wa_status.lower() == "approved"
		)

	@staticmethod
	def _upload_template_media(template, access_token, phone_number_id, api_version):
		media_type, _ = mimetypes.guess_type(template.attachment.name)
		if media_type and media_type.startswith("image/"):
			header_type = "image"
		elif media_type == "application/pdf":
			header_type = "document"
		else:
			raise ValueError("WhatsApp template attachments must be an image or PDF.")

		with open(template.attachment.path, "rb") as media_file:
			response = requests.post(
				f"https://graph.facebook.com/{api_version}/{phone_number_id}/media",
				headers={"Authorization": f"Bearer {access_token}"},
				data={"messaging_product": "whatsapp", "type": media_type},
				files={
					"file": (
						os.path.basename(template.attachment.name),
						media_file,
						media_type,
					)
				},
				timeout=60,
			)
		response.raise_for_status()
		media_id = response.json().get("id", "")
		if not media_id:
			raise ValueError("Meta media upload response did not include a media ID.")
		return {"type": header_type, "id": media_id}

	@staticmethod
	def _template_components(template: MessageTemplate, batch_lead, media_header=None):
		lead = batch_lead.lead
		values = {
			"name": lead.lead_assign_to.get_full_name() if lead.lead_assign_to else "",
			"first name": lead.lead_assign_to.first_name if lead.lead_assign_to else "",
			"company_name": "",
			"enquiry_for": lead.get_enquiry_for_display(),
			"product_name": "Product",
			"your_name": "sales team",
		}
		position_values = [lead.get_enquiry_for_display(), lead.enquiry_date.isoformat(), batch_lead.phone, batch_lead.batch.name]
		body_parameters = []
		for variable in re.findall(r"\{\{\s*([^{}]+?)\s*\}\}", template.body):
			if variable.isdigit():
				position = int(variable) - 1
				value = position_values[position] if position < len(position_values) else ""
			else:
				value = values.get(variable.lower(), "")
			body_parameters.append({"type": "text", "text": str(value)})

		components = []
		if media_header:
			media_parameter = {media_header["type"]: {"id": media_header["id"]}}
			components.append({
				"type": "header",
				"parameters": [{"type": media_header["type"], **media_parameter}],
			})
		if body_parameters:
			components.append({"type": "body", "parameters": body_parameters})
		return components