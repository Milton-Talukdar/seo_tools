# LLM Visibility Tracker — Team Notes

**Dashboard:** https://milton-talukdar.github.io/seo_tools/llm-keyword-tracker/

## What it is

A tool that checks whether ChatGPT and Perplexity recommend **Vantage Circle** when
people ask them questions like "what are the best employee recognition platforms?"

## How it works

1. We keep a list of ~15 questions our buyers typically ask (`prompts.csv`).
2. Every two weeks, an automated job sends those questions to ChatGPT and Perplexity
   (via the DataForSEO API).
3. It scans every answer: Did they mention us? Did they mention a competitor?
   Did they link to our website?
4. Results go into the dashboard, so we can see our AI "share of voice" trend
   over time and compare it against 8 competitors.

Once a month it also discovers new real user questions and finds pages where AI
quotes our content without naming us.

## How it helps us

- **Measures a channel we were blind in.** Buyers increasingly ask AI instead of
  Google. This shows if we appear in those answers.
- **Shows where competitors beat us.** If Bonusly gets mentioned and we don't,
  we know exactly which questions to target with content.
- **Finds quick wins.** When AI quotes our site without naming us ("silent
  citations"), a small content tweak can turn that into a brand mention.
- **Proof for management.** Numbers and trends, not guesses — we can show AI
  visibility improving month over month.

## Cost

About **$25/year** from our existing DataForSEO subscription. Runs fully
automatically — no manual work needed.
