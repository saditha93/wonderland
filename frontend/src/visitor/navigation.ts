export type Page =
  | "home"
  | "attractions"
  | "book"
  | "history"
  | "payment"
  | "ticket"
  | "login"
  | "profile"
  | "visits";
const pages: Page[] = [
  "home",
  "attractions",
  "book",
  "history",
  "payment",
  "ticket",
  "login",
  "profile",
  "visits",
];
export function readLocation(): { page: Page; reference: string } {
  const params = new URLSearchParams(window.location.search);
  const value = params.get("page") as Page;
  return {
    page: pages.includes(value)
      ? value
      : params.has("booking")
        ? "payment"
        : "home",
    reference: params.get("booking") ?? "",
  };
}
export function parkDate(daysAhead: number) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Colombo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(Date.now() + daysAhead * 86400000));
  const get = (type: string) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

