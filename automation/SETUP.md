# Automation setup (free, about 15 minutes)

**Status: written but not deployed or tested.** Nothing below has been run yet. Follow the steps, then use the test plan to confirm each part really works.

## How it works

```
Website form -> Google Apps Script web app -> Google Sheet row -> email to you
```

The web app runs inside your own Google account. Your sheet ID and email address are stored as Script properties inside Google, not in this repository.

## What you need

- A free Google account (a gmail.com address is fine).
- Nothing else. No payment, no card, no extra service.

## Steps (works on a phone browser in desktop mode)

1. Go to sheets.google.com and create a blank spreadsheet named **Northgate Enquiries**.
2. Copy the sheet ID from its address: the long text between `/d/` and `/edit`.
3. In the sheet, open **Extensions > Apps Script**.
4. Delete the starter code and paste the full contents of `automation/Code.gs`. Save.
5. Open **Project Settings > Script properties** and add two properties:
   - `SHEET_ID` = the ID from step 2
   - `NOTIFY_EMAIL` = the email address that should get notifications
6. Tap **Deploy > New deployment**, choose type **Web app**, set **Execute as: Me** and **Who has access: Anyone**, then deploy.
7. Google will ask you to authorize the script. It may warn that the app is "unverified". That is normal for your own script. Review the permissions (Sheets and sending email) and continue only if you are happy with them.
8. Copy the **Web app URL** (it ends in `/exec`).
9. In this repository, open `script.js`, paste the URL between the quotes in `const ENDPOINT = "";`, and commit.

If you change `Code.gs` later, you must create a **new deployment version** for the change to go live.

## Test plan

Use a made-up name and an email you control. Do not use real personal data.

| # | Test | Expected result |
|---|---|---|
| 1 | Open the Web app URL in a browser | A short message saying the endpoint is running |
| 2 | Submit the form with everything valid | Page says the enquiry was received |
| 3 | Open the Google Sheet | A header row and one new row with your values |
| 4 | Check the NOTIFY_EMAIL inbox (and spam) | An email titled "New Northgate Realty demo enquiry from ..." |
| 5 | Tap Send twice quickly | Only one row and one email |
| 6 | Submit with an invalid email | Rejected on the page; nothing saved |
| 7 | Type `=1+1` as the message | The sheet shows the text, not a calculated 2 |
| 8 | Turn off your internet and submit | The page says it could not confirm delivery |

Only describe the integration as working once tests 2 to 4 pass.

## Limits and risks

- Google lists a limit of 100 email recipients per day for consumer accounts like gmail.com. Limits can change, so check [Google's quota page](https://developers.google.com/apps-script/quotas).
- The Web app URL is public. Anyone who finds it can send data to it. The script checks inputs, ignores a hidden "honeypot" field, and ignores repeated submission IDs, but it does not stop a determined spammer.
- Never commit your sheet ID, email address, or any key to this repository.
- Not verified: whether the browser can read the script's reply on every device. Test 2 will show this. If it fails, check the script's Executions page and the sheet.

## Alternatives

Other free form or automation services exist, but I have not verified their current free-plan limits, so check them yourself before relying on them.
