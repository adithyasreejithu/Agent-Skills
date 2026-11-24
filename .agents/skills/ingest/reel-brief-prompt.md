Write the reels part of a morning brief for {date}. Below are {reel_count} short summaries of today's Instagram reels from {creators}, one JSON object per line. They were written from the reels' transcripts; treat them as the only source. Reels left out on purpose (counted, not summarized): {counted}.

Write exactly these two sections in Markdown and nothing else (no title, no preamble; the ticker table and the list of reels are added for you):

## Short read
3 to 5 bullets, 120 words at most in total, to read in 30 seconds. Lead each bullet with a bold label (for example **Mood:**, **Buying:**, **Watching:**, **Levels:**, **Lesson:**). Say who said what when creators differ.

## By creator
One `### <creator name>` heading per creator, spelled exactly as in the summaries. Under it, one line per reel, grouped by type: the point of the reel plus any levels. Merge reels that repeat the same idea.

Rules: the creators' opinions, not advice; never add your own. Every number you write must appear in the summaries, copied as stated. Do not invent tickers. Leave promotions out.

{reels}
