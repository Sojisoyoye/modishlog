export const environment = {
  production: false,
  apiBaseUrl: 'http://localhost:8000/api/v1',
  // Cloudflare Turnstile CAPTCHA on /register (task #250). Turnstile site
  // keys are meant to be public/embedded in frontend JS by design (unlike
  // the backend secret key), so no secret-handling concern here. Empty
  // means the widget never loads/renders and registration behaves exactly
  // as it does today -- matches the backend's TURNSTILE_SECRET_KEY-empty
  // no-op default.
  turnstileSiteKey: '',
};
