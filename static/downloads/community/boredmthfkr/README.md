# Community standings downloads

These files reproduce the complete fenced snippets from
`docs/example/custom-card-by.md`, **Community cards by Boredmthfkr**.

- Original design and recipe attribution: **Boredmthfkr**.
- Original community discussion: https://community.home-assistant.io/t/formula-1-racing-sensor/880842
- Packaged for the documentation on **2026-11-03**.
- The source page remains the setup and attribution reference. These are exact
  copies of its snippets, not a new combined Home Assistant package.

## Files and destinations

| File | Source snippet | Destination |
| --- | --- | --- |
| `templates.yaml` | F1 assets template helper | Merge into the template include used by `template: !include templates.yaml`; preserve existing templates |
| `drivers-standings-card.yaml` | Drivers Standings card | A Home Assistant Manual dashboard card |
| `constructors-standings-card.yaml` | Constructors Standings card | A separate Home Assistant Manual dashboard card |
| `myfont.css` | Existing font stylesheet example | `/config/www/fonts/myfont.css`; provide the licensed font separately |

The card YAML is not intended for `configuration.yaml`. Fonts, images,
button-card and sensor selection remain prerequisites documented on the page.
The recipe's external image URLs and entity IDs need checking in each setup.
Downloading these snippets does not certify the current availability of those
external resources or change the community recipe's maintenance status.

## Keeping copies aligned

When editing an inline snippet, update its corresponding download in the same
change and compare the complete UTF-8 content, including final newlines.
At packaging time the downloads matched the source blocks byte for byte:

| File | SHA-256 |
| --- | --- |
| `myfont.css` | `af38f657b0f68ac7f1eb5f753541e9aad200fc5e8d7dfc8ae696eb798f545d34` |
| `templates.yaml` | `547ec874073aaa44052099c30562ceaef84de02e09934315d1107bf25bd6be12` |
| `drivers-standings-card.yaml` | `0e4be5f54da128d7821142999ff2fef6cee8838e8b184fe17a8ebf123de9ae73` |
| `constructors-standings-card.yaml` | `048300fa309d1d8d132b494ce91c784ab81a0d83590bb046ab5c6d16901d16df` |
