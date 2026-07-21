# DentAI Skills

DentAI Skills turns a smartphone, a light-colored surface, and a safe blunt stylus with a green marker into a low-cost psychomotor training station. The browser creates a virtual route over a horizontally mirrored live camera feed, tracks the green marker locally, and measures performance. The public demo returns deterministic local feedback so anonymous use cannot generate API charges.

Live demo: https://dentai-skills-mvp.nicofin2q.chatgpt.site

## Hackathon category

Education — OpenAI Build Week 2026.

## What the prototype does

- Opens the rear smartphone camera with no native-app installation.
- Mirrors the live feed to create an indirect-vision exercise.
- Draws the route virtually; no printed route is required.
- Detects a bright green marker locally in the browser.
- Calculates precision, stability, completion, elapsed time, and a total score.
- Returns bounded local feedback that does not claim clinical competence.
- Includes an optional, disabled-by-default GPT-5.6 feedback pathway for controlled deployments.

## Privacy and safety

Camera frames are processed locally in the browser and are not uploaded or stored. The public deployment makes no OpenAI API request. Use only a capped pen or another blunt, protected object on a surface. Never use needles, sharp instruments, or perform the exercise in a person's mouth.

## Run locally

Requirements: Node.js 22.13 or newer.

```bash
npm ci
npm run dev
```

Camera access requires HTTPS or localhost. The default and public configuration returns deterministic local feedback and requires no API key. The optional server-side GPT-5.6 pathway requires both `ENABLE_OPENAI_FEEDBACK=true` and `OPENAI_API_KEY`; an API key by itself cannot activate paid requests.

## How to test

1. Open the live demo on a smartphone.
2. Place a plain light surface in view.
3. Wrap a small strip of bright green tape near the blunt end of a capped pen.
4. Tap **Prepare exercise**, then **Activate camera and begin**.
5. Allow camera access and follow the turquoise route while looking only at the screen.
6. Tap **Finish attempt** to view metrics and feedback.

## Architecture

The React client owns camera capture, mirroring, route rendering, color tracking, and metric calculation. The server validates a bounded metrics object and calls the OpenAI Responses API with `gpt-5.6` and a strict JSON schema. No image or video leaves the device.

## How Codex and GPT-5.6 were used

The project was developed during the hackathon submission period through an AI-assisted workflow in OpenAI Work and a final engineering pass in Codex. In that pass, Codex reviewed the implementation, corrected production metadata, hardened and validated the structured GPT-5.6 response handling, extended the rendered-output test, verified the build, and prepared the repository documentation and submission package. Earlier prototype iterations used real smartphone videos to simplify the setup and move the route from paper into the phone. The human builder made the key educational, product, safety, and scope decisions throughout.

GPT-5.6 contributed to the educational-feedback design and the optional structured-feedback pathway. That pathway accepts only deterministic numeric metrics and is explicitly instructed not to infer clinical competence or educational validation. It is disabled in the public demo to prevent anonymous visitors from generating API charges.

## Status

This is an educational MVP, not a clinically validated assessment system. The next phase will evaluate measurement reliability and learning outcomes with students and expert-designed rubrics.

## License

MIT. See [LICENSE](LICENSE).
