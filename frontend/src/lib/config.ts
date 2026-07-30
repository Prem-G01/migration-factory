export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

// Not a real secret -- this is a statically-built, publicly-served
// frontend, so anyone can read this out of the shipped JS bundle. It only
// raises the bar from "any script on the internet can hit the API" to
// "someone has to open devtools first" -- a deterrent against casual
// scraping/abuse, not a substitute for real per-user auth.
export const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";
