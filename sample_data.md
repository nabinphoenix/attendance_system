# Development sample accounts

These accounts are for local development and demonstration only. Change or remove them before deploying the system anywhere public.

| Role | Email | Password | Notes |
| --- | --- | --- | --- |
| Super admin | `superadmin@antimbench.example.com` | `SuperAdmin123!` | Stored as the `admin` role; use for full administration. |
| Admin | `admin@antimbench.example.com` | `Admin123!` | Academic setup, routine management, imports, and administration. |
| Routine verification student | `routine.student.verify@example.com` | `Verify123!` | Assigned to the live routine-verification section. |

## Bulk-import accounts

Student accounts created by the bulk importer receive this temporary password unless the importer is changed:

`Welcome123!`

The seeded accounts are defined in [backend/app/seed.py](backend/app/seed.py). Run the seed command after resetting a local database to recreate them.

## CPS timetable and QR-attendance test accounts

These are the local accounts provisioned by
`python -m app.test_data`. They use the CPS email convention and the password
`Welcome123!`. They are for local testing only; do not use these credentials in
a deployed system.

### Teachers

| Name | Email | Employee code | Password |
| --- | --- | --- | --- |
| Daisy Napit | `daisy.napit@cps.edu.np` | `FAC-DAISY` | `Welcome123!` |
| Dipak Poudel | `dipak.poudel@cps.edu.np` | `FAC-DIPAK` | `Welcome123!` |
| Karan Shrestha | `karan.shrestha@cps.edu.np` | `FAC-KARAN` | `Welcome123!` |
| Nisha Gnawaly | `nisha.gnawaly@cps.edu.np` | `FAC-NISHA` | `Welcome123!` |
| Shuvit Shrestha | `shuvit.shrestha@cps.edu.np` | `FAC-SHUVIT` | `Welcome123!` |

### Students

| Section | Name | Email | Roll number | Password |
| --- | --- | --- | --- | --- |
| A1 | Aarav Sharma | `aarav.sharmasep26@cps.edu.np` | `TEST-A1-01` | `Welcome123!` |
| A1 | Sita Rai | `sita.raisep26@cps.edu.np` | `TEST-A1-02` | `Welcome123!` |
| A1 | Bikash Thapa | `bikash.thapasep26@cps.edu.np` | `TEST-A1-03` | `Welcome123!` |
| A1 | Nabin Pradhan | `nabin.pradhansep26@cps.edu.np` | `TEST-A1-04` | `Welcome123!` |
| A1 | Prisha Karki | `prisha.karkisep26@cps.edu.np` | `TEST-A1-05` | `Welcome123!` |
| A2 | Aayush Dhakal | `aayush.dhakalsep26@cps.edu.np` | `TEST-A2-01` | `Welcome123!` |
| A2 | Prerana Rai | `prerana.raisep26@cps.edu.np` | `TEST-A2-02` | `Welcome123!` |
| A2 | Bibek Shrestha | `bibek.shresthasep26@cps.edu.np` | `TEST-A2-03` | `Welcome123!` |
| A2 | Sushma Gurung | `sushma.gurungsep26@cps.edu.np` | `TEST-A2-04` | `Welcome123!` |
| A2 | Ritesh Karki | `ritesh.karkisep26@cps.edu.np` | `TEST-A2-05` | `Welcome123!` |
| A3 | Nabin Nepali | `nabin.nepalisep26@cps.edu.np` | `TEST-A3-01` | `Welcome123!` |
| A3 | Rojina Thapa | `rojina.thapasep26@cps.edu.np` | `TEST-A3-02` | `Welcome123!` |
| A3 | Sagar Bista | `sagar.bistasep26@cps.edu.np` | `TEST-A3-03` | `Welcome123!` |
| A3 | Alisha Tamang | `alisha.tamangsep26@cps.edu.np` | `TEST-A3-04` | `Welcome123!` |
| A4 | Prakash Bhandari | `prakash.bhandarisep26@cps.edu.np` | `TEST-A4-01` | `Welcome123!` |
| A4 | Anju Poudel | `anju.poudelsep26@cps.edu.np` | `TEST-A4-02` | `Welcome123!` |
| A4 | Bishal Lama | `bishal.lamasep26@cps.edu.np` | `TEST-A4-03` | `Welcome123!` |
| A4 | Kritika Joshi | `kritika.joshisep26@cps.edu.np` | `TEST-A4-04` | `Welcome123!` |
| A4 | Sandesh Adhikari | `sandesh.adhikarisep26@cps.edu.np` | `TEST-A4-05` | `Welcome123!` |

> A3 has a fifth, separately created student record. It is not a sample
> account, so its personal email and password are deliberately not listed here.

### QR test for Wednesday

1. On the teacher device, sign in as `dipak.poudel@cps.edu.np` and open the
   A3 `CT071-3-3` Practical class, 06:30–08:00, in Block B / Annapurna.
2. Start the session and display its QR code.
3. On the student phone, sign in as `nabin.nepalisep26@cps.edu.np`, allow
   location and camera permissions, then scan the QR code.
