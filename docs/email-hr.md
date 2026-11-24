# Email HR

Every job page has an **Email HR about this job** card. It does the busywork; you press **Send**.

## What happens

1. **Find the address.** The first time you open a job, the app looks for the HR / recruiter mailbox, best source first:

   | Badge | Source |
   |---|---|
   | Found | An address written in the job description; the sender of the recruiter email that brought you the job; the job's own web page (mailto links, Cloudflare-protected addresses, plain text); a contact you used before for that company |
   | On their site | An address on the company's careers / contact pages, at the company's own domain |
   | Guess | `careers@`, `hr@`, `jobs@`, `talent@`, `recruitment@` at the company domain (only offered when the domain exists). **Never chosen for you** |

   Role mailboxes (`careers@`, `hr@`) rank above personal ones; `noreply@`, `sales@`, `support@`, `press@`, `legal@` and image file names are filtered out. **Search again** repeats the lookup; **Type an address** accepts any address (with an optional name that personalises the greeting).
2. **Write the email.** Subject and body come from your template (below): job title, the job board's own job ID (or `JH-<id>`), your headline and contact lines. Tick other open roles at the same company to list them in the same email. **Edit** opens the text if you want to change a word.
3. **Attach.** The job's tailored CV PDF if one exists, else the resume you uploaded in Settings; or nothing.
4. **Send.** One click sends it from your Gmail. **Save as Gmail draft** puts it in your Drafts folder instead, so you can read it in Gmail and send it yourself.

Every send is logged on the job ("You emailed … on …"), and the address is remembered for the company's next job.

## Safety rails

- Nothing is sent without your click; the API refuses without `confirm: true`.
- One email per address per `cooldown_days` (14) unless you tick **Send anyway**.
- At most `daily_cap` (25) sends per rolling 24 hours. A fresh Gmail account that blasts recruiters gets flagged.
- A failed send is logged, does not start the cool-down, and the error never contains your app password.
- The web lookup only opens public `http(s)` pages (never localhost or private addresses), at most 5 pages, 8 s each. Turn it off with `look_up_web: false`; then only the job text, recruiter sender, saved contacts and guesses are used.

## Set it up once

Settings → **CVs & email**:

1. Gmail address + app password (**Test Gmail** checks the login).
2. Resume PDF (up to 5 MB).
3. **Who signs the email**: name, phone, LinkedIn, GitHub, headline. Blank fields use `data/careerops/config/profile.yml`.

## Wording

Settings → CVs & email → **Email wording**. Plain text with `{placeholders}`; unknown ones are refused on save. Default body:

```
{greeting}

{opening}
{jobs}

I am a {role}. My resume is attached; the roles above match my recent work, and I would be glad to share more detail or speak with the hiring team.

Thank you for your time.

Regards,
{signature}
```

| Placeholder | Becomes |
|---|---|
| `{greeting}` | `Hi Asha,` when you gave or saved a name, else `Hello,` |
| `{opening}` | One job: "I am writing to apply for the X role at Y (Job ID 123)." Several: "I would like to be considered for the following roles at Y:" |
| `{jobs}` | One line per job: title, location, job ID, link |
| `{title}` `{job_id}` `{company}` `{location}` `{url}` | The main job's fields |
| `{count}` | Number of jobs listed |
| `{role}` | Your headline up to the first `\|` (default "backend engineer") |
| `{name}` `{phone}` `{linkedin}` `{github}` | Your details |
| `{signature}` | Name and any of phone / LinkedIn / GitHub, one per line |

Subjects are separate templates (`subject_one`, `subject_many`). **Reset wording to the default** restores all three.

## Limits

- Gmail only (SMTP over SSL for send, IMAP append for drafts).
- Addresses found on web pages are only as good as those pages; always glance at the **Send to** line.
- The app cannot tell whether a mailbox is read. A bounce lands in your Gmail inbox, not in the app.
