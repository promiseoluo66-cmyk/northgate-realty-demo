# Cloudflare folder — test-only boundary

This folder is included so the Worker and Studio source can be tested.

This public lab branch intentionally does not include a Wrangler deployment configuration, production database identifiers, production deployment workflows, or provider credentials. Do not run `wrangler deploy` from this branch.

Automated checks use source code and test fixtures only. They do not contact a live Cloudflare account, modify a D1 database, dispatch production rendering jobs, or call Gemini/GonkaRouter.

Production deployment is outside this lab's scope and requires a separately reviewed configuration and explicit approval.
