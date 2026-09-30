import Link from "next/link";

export function Brand() {
  return (
    <Link href="/" className="brand" aria-label="Nyaya home">
      <img src="/nyaya-mark.svg" width="46" height="46" alt="" />
      <span className="brand-copy">
        <strong>Nyaya</strong>
        <span>Evidence-Grounded Multimodal Claim Resolution Agent</span>
      </span>
    </Link>
  );
}
