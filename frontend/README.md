# frontend (Stage 2)
Static files served by Nginx: `index.html` (login, dashboard, Settings drawer, lock screen), `app.js`, `app.css`, `logo.svg`.
No build step, no external libraries, no inline scripts (strict Content-Security-Policy). The desktop is the noVNC page in a same-origin frame.
