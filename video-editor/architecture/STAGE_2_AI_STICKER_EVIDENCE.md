# Stage 2 Task 2.10 — AI sticker feasibility

**Decision: gated_optional. AI sticker generation is not enabled.**

## Candidate assessment

Stable Diffusion 3.5 is a possible self-hosted image-generation model. Stability AI's Community License includes the Stable Diffusion 3.5 suite and allows use by individuals and organisations below USD $1 million annual revenue, subject to the full licence terms. This is a conditional model licence, not a hosted inference service and not a guarantee of free compute.

## $0 compute assessment

- Cloudflare Workers Free allows 10 ms CPU per request and 128 MB memory. It cannot host or run this image-generation workload.
- The repository is public, so standard GitHub-hosted runners are documented as free and unlimited. The current `ubuntu-24.04` runner has 4 CPU cores, 16 GB RAM and 14 GB SSD, but no GPU.
- CPU image generation may be technically possible for some models, but no benchmark proves acceptable latency, memory, thermal behavior or job duration for this editor's 30-minute processing limit.
- Hosted inference APIs have changing quotas, credits and billing requirements. None is approved as a $0 dependency.

## Safety, privacy and licensing gates

Before any implementation:
- verify the exact model version and current licence, including commercial-use eligibility and attribution/redistribution conditions;
- define prompt and output safety checks and reject unsafe/untrusted imported assets;
- ensure generation runs locally in the existing private-media processing pipeline, with no media sent to an external API;
- benchmark CPU runtime or obtain an explicitly approved, genuinely free GPU route;
- store generated media in the existing private asset lifecycle and retain editable prompt/metadata records;
- test output quality, alpha/transparency, dimensions and persistence.

## Decision

Keep `ai_stickers` at `gated_optional`. Continue with editable native graphics and shapes first. Do not add an API key, credit card, paid quota or billing activation.

## Official sources

- [Stability AI licence — Community License scope and revenue threshold](https://stability.ai/license)
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [GitHub-hosted runners — public runner specifications and free usage](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
