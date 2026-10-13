export type Attraction = {
  id: string;
  name: string;
  description: string;
  category: string;
  thrill_level: "gentle" | "moderate" | "high";
  minimum_age: number;
  minimum_height_cm: number;
  operational_status: "open" | "maintenance" | "retired";
};
export type Tier = {
  id: string;
  name: string;
  min_guests: number;
  max_guests: number;
  price_cents: number;
  currency: string;
};
export type Booking = {
  reference: string;
  tier_id: string;
  tier_name: string;
  guest_count: number;
  visit_date: string;
  time_slot: string;
  amount_cents: number;
  currency: string;
  status: "pending" | "confirmed";
  payment_status: "unpaid" | "paid";
  created_at: string;
  confirmed_at: string | null;
};
export type Ticket = {
  booking: Booking;
  qr_data_url: string;
  ticket_token: string;
};
export type Checkout = {
  reference: string;
  provider: "local" | "stripe";
  checkout_url: string | null;
};
export const money = (cents: number, currency = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency }).format(
    cents / 100,
  );

export async function api<T>(
  path: string,
  token = "",
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {
    ...options,
    headers,
    cache: "no-store",
  });
  const body: unknown = await response.json();
  if (!response.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? body.detail
        : undefined;
    throw new Error(
      typeof detail === "string"
        ? detail
        : "Please check your input and try again.",
    );
  }
  return body as T;
}
