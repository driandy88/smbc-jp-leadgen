/** Score and Field: the original click-through design pages, unchanged apart from a nav bridge. */
export function DesignFrame({ page }: { page: "score" | "field" }) {
  const file = page === "score" ? "Score" : "Field";
  return (
    <iframe
      key={page}
      title={`Hexline ${file}`}
      src={`/design/${file}.dc.html`}
      style={{ border: "none", width: "100%", height: "100vh", display: "block", background: "#F3F0E8" }}
    />
  );
}
