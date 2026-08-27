import axios from "axios";
// Default to the same origin so a phone can use the Next.js proxy instead of
// trying to reach its own localhost:8000.
const api = axios.create({ baseURL: process.env.NEXT_PUBLIC_API_URL || "", withCredentials: true });
export default api;
