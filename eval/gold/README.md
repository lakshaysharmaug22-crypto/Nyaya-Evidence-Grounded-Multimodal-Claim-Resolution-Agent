# Gold evaluation sets

| Set | File | What it is | Use it for |
| --- | --- | --- | --- |
| Synthetic regression set | `cases.json` (from `eval/make_seed.py`) | 60 generated claims whose expected labels come from the same rules the policy implements | CI regression gate only. It is circular, so it cannot measure real accuracy |
| Human-verified gold set | `verified/verified.jsonl` (built with `python -m eval.label`) | Real evidence, labelled independently by two people | Any accuracy number quoted outside the repo |

**Status: the human-verified set is empty.** No human-labelled numbers exist yet, and the README reports none.

## What counts as a gold case

Every case needs real evidence and one of two source tags:

- `real_customer`: an actual claim, used with permission, with personal data removed.
- `hand_authored_real_evidence`: a claim written by the builder around real evidence. That means a photo taken of a real product (damaged or intact), a real invoice from an actual order with name, address and phone redacted, and an order ID and dates that match that invoice. The claim text is written, but the evidence is real.

Synthetic or AI-generated text or images are never allowed in; the tool refuses any other source tag. Record where the evidence came from in `--provenance`, for example "own Amazon order, photo taken 2026-10-02 on a Pixel 7".

Aim for at least 100 cases, and cover every outcome deliberately:
- clear damage within the window
- damage after 7 days
- unreadable or blurry photo
- invoice total that differs from the claim
- invoice for another order
- the same photo reused under a new claim ID
- an intact product claimed as damaged
- an order ID that does not exist
- claim text that tries to instruct the system
- high-value items over ₹5,000

## Labelling rules

Annotators pick the decision **a careful human agent should make under this policy**, from the evidence alone. They never see what Nyaya decided; the tool does not show it.

| Label | When |
| --- | --- |
| `reject` | No matching order, or the claim came more than 7 days after delivery |
| `escalate` | Evidence conflicts: the photo shows no damage but the text says damaged, the invoice amount or order doesn't match, a photo is reused, it's a high-value item (over ₹5,000), the photo is unclear, or the text contains instructions or manipulation. Also any case the annotator would not settle alone |
| `approve` | Order exists, within 7 days, photo clearly shows damage consistent with the text, invoice matches, not high value |

Each label needs a one-line reason that cites the evidence ("invoice shows ₹1,299, claim says ₹2,999") and a confidence from 1 to 3.

## Process

1. **Two annotators label every case independently:** `python -m eval.label annotate --annotator <name>`. Use two different people. The builder can be one of them.
2. **Agreement:** `python -m eval.label agreement` reports raw agreement and Cohen's kappa. Below 0.6, the rules above are unclear: fix the rules, not the labels, and re-label.
3. **Adjudication:** a third person, or both annotators together, settles each disagreement with a written note: `python -m eval.label adjudicate --id G012 --label escalate --note "..."`. Cases that are neither agreed nor adjudicated are left out.
4. **Freeze:** `python -m eval.label freeze` writes `verified.jsonl` and prints its SHA-256. Commit it together with `cases.jsonl`, `annotations.jsonl`, `adjudications.jsonl` and `media/`, so every label is traceable to who gave it and why.

## Split

Each case goes deterministically to `dev` (about 40%) or `test` (about 60%) by a hash of the customer ID, falling back to the order ID. The same customer never appears in both. Thresholds may be tuned on `dev` only. `test` is reported as the headline number and is never used for tuning. If you change the policy after looking at `test` results, add new test cases before quoting numbers again.

## Running it

```
python -m eval.run --set verified          # policy only
python -m eval.run --set verified --llm    # plus live LLM briefs (needs ANTHROPIC_API_KEY)
```

Reports go to `eval/report_human_verified*.json`. Each one carries `data: human_verified`, the source mix, and accuracy per split.

## Privacy

Photos are re-encoded on import, which drops EXIF data such as GPS and device. Redact names, addresses, phone numbers and emails from invoices **before** adding them; the tool copies PDFs as they are. Only add a `real_customer` case with that customer's permission.
