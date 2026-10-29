# IONOS mailbox setup

IONOS is an inbound IMAP provider. Campaign sending remains on Mailgun. A tenant can connect its mailbox from **Email Settings → Email reply tracking → IONOS**. Connecting tests IMAP SSL login and stores the password encrypted with the existing `GMAIL_TOKEN_ENCRYPTION_KEY`; the API never returns the password or ciphertext.

The default server settings are `imap.ionos.com:993` over SSL/TLS. Optional trusted backend environment overrides are:

- `IONOS_IMAP_HOST` (default `imap.ionos.com`)
- `IONOS_IMAP_PORT` (default `993`)
- `IONOS_IMAP_TIMEOUT_SECONDS` (default `15`)

Do not accept host or port values from the frontend. The existing `GMAIL_TOKEN_ENCRYPTION_KEY` must be configured as a valid Fernet key and kept stable so stored credentials remain decryptable. Add these settings to the backend environment; this feature does not require Google OAuth credentials.

## Migrations and sync

Apply the schema migration from the Django project directory:

```powershell
python manage.py migrate
```

Run a manual synchronization with:

```powershell
python manage.py sync_ionos_replies
```

The command polls every connected tenant mailbox. Connect-time synchronization starts after the latest UID already in the inbox, so replies received before connecting are not imported. The service serializes syncs per mailbox with a database row lock, advances its UID cursor only after successful processing, and stores unmatched messages in the tenant's existing Incoming Replies inbox.

No application scheduler is configured in this project. For automatic polling, schedule the command every five minutes with the operating system scheduler. On Windows Task Scheduler, run the project's Python executable with arguments `manage.py sync_ionos_replies` and set **Start in** to the `email_compaign` backend directory. On Linux, an example crontab entry is:

```cron
*/5 * * * * cd /path/to/email_compaign && /path/to/venv/bin/python manage.py sync_ionos_replies
```

Use the same environment and database configuration as the Django application. The app's existing Gmail synchronization remains a separate command, `python manage.py sync_gmail_replies`.

When sending a campaign, an explicitly configured campaign, tenant Mailgun, or tenant campaign reply-to address takes precedence. If none is set, a connected IONOS mailbox is used as the reply-to address; Mailgun continues to send the message.
