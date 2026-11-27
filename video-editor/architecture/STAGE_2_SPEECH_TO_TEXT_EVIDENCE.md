# Stage 2 Task 2.5 — Speech-to-text feasibility

**Decision: gated_optional. Automatic transcription is not enabled.**

## Candidate assessment

OpenAI Whisper is a general-purpose multilingual speech-recognition model. Its repository states that both code and model weights are released under the MIT License. The official model table ranges from tiny (39 million parameters) through large (1.55 billion parameters), with trade-offs in speed and accuracy.

The `whisper.cpp` implementation supports CPU-only inference. Its published memory table lists the tiny model at about 75 MiB on disk and 273 MB memory, and base at about 142 MiB on disk and 388 MB memory. This is a credible local inference candidate without a paid ASR API.

## $0 compute and architecture

This repository is public. GitHub's standard public Linux hosted runner is documented as free and unlimited for public repositories, with 4 CPU cores, 16 GB RAM and 14 GB SSD for `ubuntu-24.04`. The current editor workflow already uses that runner and has a 30-minute job timeout.

Cloudflare Workers Free is not a suitable model host: its documented limits are 10 ms CPU per request and 128 MB memory. Whisper inference must run in the existing GitHub Actions processing stage, not inside the Worker.

The app can keep using the existing private Release asset path and process audio on the runner. No audio should be sent to a third-party transcription API. Workflow logs must not print transcript contents, source audio or sensitive metadata.

## Why it remains gated

No representative real-footage benchmark has been accepted. Before enabling, measure:
- word error rate across the intended languages, accents and noisy/music-backed footage;
- word timestamp drift and segmentation quality against hand-labelled references;
- CPU runtime for short, medium and long videos within the existing 30-minute job limit;
- peak memory and temporary disk use;
- hallucinations on silence/music and failure behavior on unsupported codecs;
- privacy-safe logs and deletion of temporary media/model artifacts.

Automatic transcription must create editable transcript records only. It must never automatically delete words, pauses or clips. The user must review transcript content and timestamps before transcript-driven editing.

## Decision

Keep `auto_captions` at `gated_optional`. Continue to support imported user-supplied timed transcripts. Do not add a paid provider, API key, credit requirement or billing activation.

## Official sources

- [OpenAI Whisper README — model sizes, multilingual support and MIT code/weight licence](https://github.com/openai/whisper)
- [OpenAI Whisper MIT licence](https://github.com/openai/whisper/blob/main/LICENSE)
- [whisper.cpp — CPU-only inference and model disk/memory requirements](https://github.com/ggml-org/whisper.cpp)
- [GitHub-hosted runners — public-repository pricing and runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Cloudflare Workers limits — Free CPU and memory](https://developers.cloudflare.com/workers/platform/limits/)
