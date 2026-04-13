# Legal Data Sources — Vani-Kanoon

## Disclaimer

> **IMPORTANT:** The legal information provided through Vani-Kanoon is for **informational purposes only** and does **not** constitute legal advice. Laws change frequently and may have been amended after the data was last updated. Always consult a qualified, licensed lawyer for advice specific to your situation.

---

## 1. Indian Penal Code (IPC) Data

**File:** `ai-service/data/ipc_sections.json`

**Source:** The Indian Penal Code, 1860 (Act No. 45 of 1860)

**Official References:**
- India Code Digital Repository: https://indiacode.nic.in/handle/123456789/2263
- Ministry of Law & Justice — Legislative Department
- Bare Act published by Government of India

**Coverage:** 50+ key sections including Sections 107, 120B, 143, 147, 299–304B, 307–309, 319–325, 354–354D, 375–376, 378–395, 403–406, 415–420, 441–448, 463–471, 493–498A, 499–509.

**Last Updated:** Based on amendments up to Criminal Law (Amendment) Act 2013.

**How to update:** Download the latest bare act from India Code and update section descriptions and punishment details accordingly.

---

## 2. Bharatiya Nyaya Sanhita (BNS) 2023 Data

**File:** `ai-service/data/bns_sections.json`

**Source:** Bharatiya Nyaya Sanhita, 2023 (Act No. 45 of 2023) — replaces IPC from July 1, 2024.

**Official References:**
- Ministry of Home Affairs — https://mha.gov.in
- Gazette of India Extraordinary, Part II, Section 1
- India Code: https://indiacode.nic.in

**Coverage:** 30+ sections covering offences against the body (Sections 63–66, 80, 85, 101–118), property offences (303–329), defamation (356–358), criminal intimidation (351), and new provisions for organised crime (111) and national security (152).

**Key Change:** BNS replaces IPC 1860. IPC→BNS mapping is maintained in `legal_processor.py` (`IPC_TO_BNS_MAP`).

**How to update:** Refer to the official Gazette notification and update section texts. Run `map_ipc_to_bns()` tests after any changes.

---

## 3. Tenancy Laws Data

**File:** `ai-service/data/tenancy_act.json`

**Sources:**

| Document | Source |
|----------|--------|
| Model Tenancy Act 2021 | Ministry of Housing & Urban Affairs — https://mohua.gov.in |
| Karnataka Rent Control Act 2001 | Karnataka Gazette Notification |
| Maharashtra Rent Control Act 1999 | Maharashtra Government Gazette |
| Tamil Nadu Regulation Act 2017 | Tamil Nadu Government Gazette |
| Delhi Rent Act 1958 | India Code |
| Telangana Rent Control | Telangana Government |

**Coverage:** Security deposit limits, notice periods, eviction grounds, rent increase rules, dispute forums, state-specific variations.

**How to update:**
1. Check state government official gazettes for amendments.
2. Update `state_variations` section in `tenancy_act.json`.
3. Cross-check dispute forum details with respective state judiciary websites.

---

## 4. Family Law Data

**File:** `ai-service/data/family_law.json`

**Sources:**

| Act | Source |
|-----|--------|
| Hindu Marriage Act 1955 | India Code — Act No. 25 of 1955 |
| Hindu Succession Act 1956 | India Code — Act No. 30 of 1956 (as amended 2005) |
| Special Marriage Act 1954 | India Code — Act No. 43 of 1954 |
| Muslim Personal Law (Shariat) Application Act 1937 | India Code |
| Muslim Women (Protection of Rights on Marriage) Act 2019 | Gazette of India 2019 |
| Christian Marriage Act 1872 | India Code |
| Indian Divorce Act 1869 | India Code |
| Protection of Women from Domestic Violence Act 2005 | India Code — Act No. 43 of 2005 |

**Note on Muslim Personal Law:** Muslim personal law is not codified in a single statute. The information provided is based on established jurisprudence and the 1937 Act. Triple Talaq is now criminalized under the 2019 Act.

**How to update:**
- Check Supreme Court and High Court judgments for landmark interpretations.
- Monitor Parliament for amendments (e.g., Uniform Civil Code developments).

---

## 5. Property Law Data

**File:** `ai-service/data/property_law.json`

**Sources:**

| Act | Source |
|-----|--------|
| Transfer of Property Act 1882 | India Code — Act No. 4 of 1882 |
| Registration Act 1908 | India Code — Act No. 16 of 1908 |
| Indian Stamp Act 1899 | India Code — Act No. 2 of 1899 |
| RERA 2016 | MoHUA — https://rera.mohua.gov.in |
| RFCTLARR Act 2013 | India Code — Act No. 30 of 2013 |

**Stamp Duty Rates:** Rates vary by state. Data current as of 2023–24. Always verify current rates with the state's stamp duty authority or sub-registrar office.

**How to update:**
- RERA: Check individual state RERA portals for state-specific rules.
- Stamp duty: Verify with state Revenue/Registration departments annually.

---

## 6. State Laws Data

**File:** `ai-service/data/state_laws.json`

**Coverage:** Karnataka, Maharashtra, Tamil Nadu, Delhi, Telangana, Rajasthan, Gujarat.

**Sources:**
- Individual state government gazette notifications
- High Court websites for court information
- State registration department websites for stamp duty

**Expanding to new states:**
1. Add a new key under `states` in `state_laws.json`.
2. Include `tenancy`, `courts`, `key_acts`, and `stamp_duty` sections.
3. Update `location_service.py` `STATE_NAME_MAP` with city→state mappings.

---

## 7. Dialect Mapping Data

**File:** `ai-service/data/dialect_mapping.json`

**Sources:**
- Linguistic Survey of India
- Central Institute of Indian Languages (CIIL), Mysuru
- Academic research papers on Indian dialects
- Community linguist consultations

**Coverage:** Kannada (4 dialects), Hindi (4 dialects), Marathi (4 dialects), Tamil (3 dialects), Telugu (3 dialects), English (1 variety).

**How to update:** Add new dialect entries under the relevant language with `name`, `region`, `districts`, `keywords`, `tone`, and `sample_phrases`.

---

## General Update Instructions

1. **Version control all changes** — each data update should be a separate git commit.
2. **Test after updates** — run the legal processor tests to ensure keyword matching still works.
3. **Document the source** — always note the gazette number / section number of the source when updating.
4. **Date stamp** — add an `"updated_date"` field to each JSON file when making changes.

---

## Useful Official Sources

| Resource | URL |
|----------|-----|
| India Code (all Central Acts) | https://indiacode.nic.in |
| Ministry of Law & Justice | https://lawmin.gov.in |
| Supreme Court of India | https://sci.gov.in |
| National Legal Services Authority | https://nalsa.gov.in |
| Ministry of Housing & Urban Affairs | https://mohua.gov.in |
| RERA Portal | https://rera.mohua.gov.in |
| e-Courts (all courts) | https://ecourts.gov.in |
