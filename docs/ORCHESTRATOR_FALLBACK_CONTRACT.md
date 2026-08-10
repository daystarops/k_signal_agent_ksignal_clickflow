# Orchestrator Fallback Contract

Instagram routing is Apify → browser capture → manual URL queue. Provider outcomes and elapsed time are logged before routing. `LOGIN_REQUIRED`, `PRIVATE_ACCOUNT`, and `ROBOTS_DENIED` terminate as denied. Timeout is degraded and may enter the manual queue. Providers do not own routing.

