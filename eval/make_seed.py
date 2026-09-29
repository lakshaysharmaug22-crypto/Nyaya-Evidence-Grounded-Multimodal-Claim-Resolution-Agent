import json, random
random.seed(7)
cases = []
for i in range(60):
    kind = random.choice(["clear", "clear", "clear", "window", "dup", "mismatch", "lowconf", "noorder", "textmismatch"])
    claim = {"id": f"C{i:03d}", "order_id": f"ORD{i:04d}", "damage_conf": 0.95,
             "amount_inr": random.choice([499, 1499, 2999]), "days_since_delivery": 2,
             "text": "box was crushed and the item is broken"}
    exp = "approve"
    if kind == "window": claim["days_since_delivery"] = 12; exp = "reject"
    if kind == "dup": claim["duplicate_image"] = True; exp = "escalate"
    if kind == "mismatch": claim["modalities_agree"] = False; exp = "escalate"
    if kind == "lowconf": claim["damage_conf"] = 0.6; exp = "escalate"
    if kind == "noorder": claim["order_id"] = f"BAD{i}"; exp = "reject"
    if kind == "textmismatch": claim["damage_conf"] = 0.1; exp = "escalate"
    cases.append({"claim": claim, "expected": exp})
json.dump(cases, open("eval/gold/cases.json", "w"), indent=1)
print(len(cases))
