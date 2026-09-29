export type Item = { id: string; who: string; amt: number; conf: number; claim: Record<string, unknown> };

export const QUEUE: Item[] = [
  { id: "C-101", who: "Asha R.", amt: 1499, conf: 0.95, claim: { id: "C-101", order_id: "ORD101", text: "box was crushed and the item is broken", damage_conf: 0.95, amount_inr: 1499, days_since_delivery: 2 } },
  { id: "C-102", who: "Vikram S.", amt: 999, conf: 0.93, claim: { id: "C-102", order_id: "ORD102", text: "product came with a dent and scratches", damage_conf: 0.93, amount_inr: 999, days_since_delivery: 1 } },
  { id: "C-103", who: "Neha T.", amt: 2999, conf: 0.61, claim: { id: "C-103", order_id: "ORD103", text: "received it damaged, photo attached", damage_conf: 0.61, amount_inr: 2999, days_since_delivery: 3 } },
  { id: "C-104", who: "Rohit K.", amt: 1499, conf: 0.9, claim: { id: "C-104", order_id: "ORD104", text: "screen is cracked when it arrived", damage_conf: 0.9, amount_inr: 1499, days_since_delivery: 12 } },
];
