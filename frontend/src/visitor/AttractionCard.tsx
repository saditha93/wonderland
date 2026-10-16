import { type Attraction } from "../shared/api";
export function AttractionCard({
  attraction,
  onSelect,
}: {
  attraction: Attraction;
  onSelect: () => void;
}) {
  const categoryClass =
    attraction.thrill_level === "high"
      ? "thrill"
      : attraction.category === "Water ride"
        ? "water"
        : "gentle";
  return (
    <article className="attraction-card">
      <div className={`attraction-art ${categoryClass}`} aria-hidden="true">
        <span>
          {attraction.thrill_level === "high"
            ? "↟"
            : attraction.category === "Water ride"
              ? "≈"
              : "✳"}
        </span>
        <div className="art-orbit" />
      </div>
      <div className="attraction-copy">
        <div className="card-meta">
          <span>{attraction.category}</span>
          <span className="capitalize">{attraction.operational_status}</span>
        </div>
        <h3>{attraction.name}</h3>
        <p>{attraction.description}</p>
        <p className="guidance">
          {attraction.thrill_level} thrill ·{" "}
          {attraction.minimum_height_cm
            ? `${attraction.minimum_height_cm}+ cm`
            : "All heights"}
        </p>
        <button className="text-button" onClick={onSelect}>
          Explore attraction →
        </button>
      </div>
    </article>
  );
}
