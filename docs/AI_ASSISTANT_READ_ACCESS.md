# AI assistant read access

The administrative AI assistant only has allowlisted, read-only tools. It never receives a database connection, may return at most 50 database/import records or 100 Google Form responses per tool call, and remains limited to the administrator's active college.

## Application database

Use `get_database_catalog` before `read_database_records`. The catalog exposes operational datasets and safe columns only. Passwords, credentials, reset/session data, contact details, IP/location data, tokens, encrypted values, private message bodies, audit payloads, and approval data are excluded.

## CSV and Excel imports

The application stores import-job outcomes and row results, not the original uploaded file. `get_import_history` lets the assistant read those stored outcomes. Contact data in saved row results is redacted before it reaches an AI provider.

## Connected Google Drive files

The current Google Workspace connection is college-scoped and managed from Admin → Google Workspace. After connecting the admin's Workspace account, the page lists files that account can access. An existing connection created before Drive listing was added must be authorized once more with **Update Google permissions**. The added `drive.metadata.readonly` scope is used to list file metadata; Forms and Sheets content is read through their respective APIs. The Google OAuth project must have the Drive, Forms, and Sheets APIs enabled and allow the requested scopes.

Admins can preview Google Form questions, optionally open its respondent-facing form, page through responses, preview up to 100 rows × 26 columns of a Sheet tab, or open the original file on Google for full editing. The in-app preview is read-only. Opening the live respondent form can submit a real response.

From a selected Form or Sheet, **Analyze with AI** opens the assistant with that file selected. The assistant reads only the selected file, at most 100 Form responses or a bounded Sheet range per call. Respondent email, contact details, and answers under student/respondent identity headings are omitted or redacted before the data reaches the model. Google file contents are treated as untrusted data. The analysis should not identify respondents and should distinguish evidence from interpretation.

The current assistant uses the configured cloud AI provider. When an admin submits a request, the prompt and the minimum selected-file data returned by the read-only tool are sent to that provider; provider API keys remain on the backend. Do not use this flow for data that must remain entirely on premises unless the deployment is configured to use an approved local model.

## Legacy single-form connection

The `get_google_form_responses` tool and `GOOGLE_FORMS_*` settings below are a separate legacy integration for one statically configured form. New feedback workflows should use the college's Google Workspace connection and the Drive browser above.


The `get_google_form_responses` tool is disabled unless all required server-side settings are configured. It uses only `GET` requests to Google Forms and never modifies a form or its responses.

1. Enable the Google Forms API in the Google Cloud project.
2. Authorize the Google account that can read the target form using the `https://www.googleapis.com/auth/forms.responses.readonly` scope. Add `https://www.googleapis.com/auth/forms.body.readonly` to map answer IDs to question titles.
3. Configure these secrets on the backend and in Elastic Beanstalk; never expose them with `NEXT_PUBLIC_` variables or commit them:

   ```text
   GOOGLE_FORMS_ENABLED=true
   GOOGLE_FORMS_FORM_ID=<form ID>
   GOOGLE_FORMS_OAUTH_CLIENT_ID=<OAuth client ID>
   GOOGLE_FORMS_OAUTH_CLIENT_SECRET=<OAuth client secret>
   GOOGLE_FORMS_OAUTH_REFRESH_TOKEN=<offline refresh token>
   ```

   `GOOGLE_FORMS_ACCESS_TOKEN` is supported only for short-lived/manual testing. The OAuth client, secret, and refresh token are the production configuration.

4. The token must be granted access to the specific form. After changing Elastic Beanstalk environment settings, wait for the API service to restart and use the assistant to request a small page of responses.

Google's Forms API documents the read-only response endpoint at `GET /v1/forms/{formId}/responses` and its required authorization scopes:
<https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses/list>

Form answers are treated as untrusted input. Respondent email and answers to fields labelled as email, phone, address, password, or location are redacted before the model sees them.
