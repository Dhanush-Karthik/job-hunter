These fixtures are sanitized MIME copies of the supplied samples, plus clearly labelled
synthetic examples (`X-Jobhunter-Synthetic: yes`). Reconstructed input retains its
`X-Jobhunter-Reconstructed` header. No original transport headers or message IDs are retained.
Names, recipient and personal addresses, phone numbers, query tracking, and opaque
tracking/session tokens are removed or replaced. Company names, advertised titles,
and HTML card structures are preserved. Opaque Wellfound links use distinct fake paths.

LinkedIn, Cutshort, Instahyre and Wellfound alerts have supplied real samples. Naukri,
Hirist, Foundit and Uplers alert formats are synthetic only; the supplied Naukri sample
is personal recruiter outreach, not a digest. Synthetic alerts are format approximations,
not evidence of compatibility with unseen production mail.

The Instahyre profile reminder is under `other`: it contains preferences rather than
job cards. The supplied Amazon rejection sample has a status-update subject but no
readable decision body. It must produce `needs_eyes`, never an inferred rejection.
The Amazon assessment-completed message is an acknowledgement, not another invitation.

The `regression-*` samples are seven sanitized messages from the mailbox classification
audit. Indeed's two digests contain 21 and 27 cards. Supabase, Adobe and Glassdoor mail
are marketing and produce no proposals. The two LinkedIn InMail notifications belong
to one Liquidnitro Games conversation. Original platform sender account names are kept;
personal names and tracking paths are replaced. The earlier InMail fixtures now also
retain their original platform account names. Indeed is verified on supplied real mail.
