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
