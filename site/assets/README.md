# Cat Track media

Full-size public photo copies live in [`media/`](../../media/). Their image data is unchanged; private metadata is removed, while color profiles and any orientation needed to display the image correctly are retained. The optimized WebP exports have orientation baked in. No cat identity has been assigned to individual photos.

Private originals remain untouched in the local project root and are excluded from the public repository. The removed video is not published.

| Asset | Source | Dimensions | Bytes |
| --- | --- | --- | ---: |
| `ax3-hand.jpeg` | [`media/ax3_hand_1.jpeg`](../../media/ax3_hand_1.jpeg) | 567 × 600 | 57104 |
| `cart-cat.webp` | [`media/8A3A7486.JPG`](../../media/8A3A7486.JPG) | 1600 × 2399 | 128854 |
| `cart-cat-800.webp` | [`media/8A3A7486.JPG`](../../media/8A3A7486.JPG) | 800 × 1199 | 47646 |
| `chair-cat.webp` | [`media/8A3A7949.JPG`](../../media/8A3A7949.JPG) | 1600 × 2399 | 180910 |
| `chair-cat-800.webp` | [`media/8A3A7949.JPG`](../../media/8A3A7949.JPG) | 800 × 1199 | 49706 |
| `together.webp` | [`media/T&p1.png`](../../media/T&p1.png) | 1600 × 1383 | 361900 |
| `together-800.webp` | [`media/T&p1.png`](../../media/T&p1.png) | 800 × 692 | 95628 |
| `cat-track-palette.webp` | Generated editorial illustration | 1586 × 992 | 168896 |

Photos use WebP quality 84. The project thumbnail uses quality 87.

Suggested image descriptions:

- Cart: A fluffy striped cat sitting in a small wooden toy shopping cart.
- Chair: A cream-colored cat reclining on a chair beneath a row of coats.
- Together: Two fluffy cats sprawled side by side on a gray sofa.
- Project thumbnail: Two cats wearing small activity trackers, with red and blue movement traces flowing around them.

## Project thumbnail generation

Generated using the built-in image generation tool, following `Todd dot sh/docs/thumbnail-art-direction.md`. This is a decorative illustration, not a photograph of the cats or a measured data visualization.

The public generated illustration is [`cat-track-palette.webp`](cat-track-palette.webp).

Final prompt:

```text
Use case: stylized-concept.
Asset type: 16:10 landscape website project-card thumbnail in a unified editorial series.

Style: sophisticated tactile paper and softly rendered 3D editorial illustration; contemporary magazine art; crisp, premium, restrained.

Fixed palette: warm white #F4F1EA, ink black #1D1C19, stone gray #8D887E, signal red #B64832, deep blue #31566B, muted ochre #B58A43. Use only these six color families and natural lighter or darker values caused by lighting. Warm white, black, and gray should dominate; red, blue, and ochre are restrained accents.

Constraints: preserve a 16:10 composition, tactile materials, soft directional studio light, subtle shadows, and generous breathing room.

Avoid: green, cyan, turquoise, purple, magenta, bright orange, bright yellow, any other hue, text, letters, numbers, logos, trademarks, and watermarks.

Project subject: Cat Track, a personal data exploration of two fluffy house cats' activity and long naps. A pair of beautifully sculpted tactile paper cats resting close together on a warm white subtly textured paper floor: one fluffy pale stone-gray cat with dark charcoal tabby stripes on its face and tail, and one fluffy cream-white cat with subtly ochre-shaded ears and tail. Make them calm and charming, with natural feline anatomy and generous soft fur volume interpreted as delicate layered paper, not cartoon mascots. Each wears a very small simple unbranded accelerometer collar tag, one muted red and one deep blue. Two thin paper activity traces, one signal red and one deep blue, flow gently across the lower foreground and arc around the pair; varied low organic wavelets imply activity measurement, with no graph grid, no arrows, and no UI panels. Main subjects fully inside image bounds and composed centrally with ample empty margin. Contemporary editorial still-life, gentle three-quarter view, soft directional studio light from upper left, warm white background occupying the entire image. Exact 16:10 landscape composition.
```
