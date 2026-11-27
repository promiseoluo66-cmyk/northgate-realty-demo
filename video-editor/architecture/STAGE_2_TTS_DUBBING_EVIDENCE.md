# Stage 2 Task 2.12 — TTS and dubbing feasibility

**Decision: gated_optional. TTS and dubbing are not enabled.**

## Candidate assessment

Piper is a local neural text-to-speech engine. The current `OHF-Voice/piper1-gpl` repository is GPL-3.0-or-later. This is an open-source licence, but distributing or integrating the engine requires a GPL compliance review.

Piper does not grant one blanket licence for every voice. Its official licensing guide says each voice's `MODEL_CARD` and full fine-tuning chain must be checked. A voice may inherit restrictions from an earlier base model even if its own dataset licence looks permissive. The guide specifically warns that common Lessac-derived voices are research-only/non-commercial. The commercial-use list separately identifies voices whose full dataset chain permits commercial use, including public-domain and Creative Commons cases.

A public-domain or permissively licensed voice could be evaluated later, but no exact model has been selected, approved or tested in this editor.

## $0 compute assessment

- Cloudflare Workers Free has 10 ms CPU per request and 128 MB memory; it is not a TTS inference host.
- The public GitHub Actions runner offers a free CPU route, but this project has not benchmarked synthesis speed, peak memory, model download size or multilingual output under its 30-minute job limit.
- No paid TTS API, subscription, trial credit or billing activation is approved.

## Required gates

Before enabling:
- review the exact engine licence and comply with source/redistribution obligations;
- inspect the exact voice `MODEL_CARD`, dataset licence and every upstream fine-tuning voice in its chain;
- confirm commercial use and redistribution rights for the app's actual use;
- test pronunciation, naturalness, accents, language coverage, timing, audio quality and alignment against human review;
- verify private processing, temporary-file cleanup and persistence of generated audio;
- require the user to approve generated speech before it replaces or mixes with original audio.

No voice cloning, imitation of a real person's voice, automatic translation or unreviewed dubbing is included.

## Decision

Keep `tts_dubbing` and `tts_audio` at `gated_optional`. No voice model or synthesis service is bundled.

## Official sources

- [Piper voice licensing — engine and model-card/training-chain distinctions](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/LICENSING.md)
- [Piper commercial-use list — voice models with permissive training chains](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/COMMERCIAL_USE.md)
- [Piper repository — GPL-3.0-or-later engine](https://github.com/OHF-Voice/piper1-gpl)
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [GitHub-hosted runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
