import tote from "@/assets/p-tote.jpg";
import duffel from "@/assets/p-duffel.jpg";
import notebook from "@/assets/p-notebook.jpg";
import sketchbook from "@/assets/p-sketchbook.jpg";
import knife from "@/assets/p-knife.jpg";
import mug from "@/assets/p-mug.jpg";
import cap from "@/assets/p-cap.jpg";
import repair from "@/assets/p-repair.jpg";
import lifestyle from "@/assets/lifestyle.jpg";
import story from "@/assets/story.jpg";

export type CategorySlug = "bags" | "notebooks" | "tools";

export const categories: { slug: CategorySlug; name: string; intro: string }[] = [
  {
    slug: "bags",
    name: "Bags",
    intro:
      "Canvas and leather carriers built to haul firewood, groceries and a paperback — and to look better after ten years of it.",
  },
  {
    slug: "notebooks",
    name: "Notebooks",
    intro:
      "Paper that takes pencil, ink and a little rain. Sized for back pockets and map tables alike.",
  },
  {
    slug: "tools",
    name: "Field Tools",
    intro:
      "Small, honest tools for camp and kitchen: things you reach for every weekend and never think about again.",
  },
];

export type GalleryImage = { src: string; alt: string; zoom?: boolean };
export type Review = {
  name: string;
  date: string;
  rating: number;
  title: string;
  body: string;
  verified?: boolean;
};
export type VariantGroup = { name: string; options: string[] };

export type Product = {
  slug: string;
  name: string;
  tagline: string;
  description: string[];
  category: CategorySlug;
  price: number;
  compareAt?: number | undefined;
  sku: string;
  rating: number;
  reviewCount: number;
  histogram: [number, number, number, number, number]; // 5★ → 1★ counts
  stock: "in" | "low" | "out";
  stockLeft?: number;
  images: GalleryImage[];
  variants: VariantGroup[];
  highlights: string[];
  specs: Record<string, string>;
  care: string;
  related: string[];
  reviews: Review[];
  featured?: boolean;
};

export const storyImage = story;

const g = (src: string, name: string): GalleryImage[] => [
  { src, alt: `${name}, front view` },
  { src, alt: `${name}, detail`, zoom: true },
  { src: lifestyle, alt: `${name} at camp by the river` },
];

export const products: Product[] = [
  {
    slug: "field-tote",
    name: "Field Tote",
    tagline: "A heavy canvas carryall for markets, beaches and the long way home.",
    description: [
      "The Field Tote is cut from 18 oz cotton duck and finished with vegetable-tanned leather handles that darken with use. It stands up on its own, swallows a week of groceries, and still folds flat behind the seat of a truck.",
      "Inside, a single slip pocket keeps keys and a phone out of the sand. The base is double-layered and bar-tacked at every stress point, so it will carry a cast-iron pan as happily as a towel.",
      "We sew every tote in small batches in Portland. No two pairs of handles age quite the same way.",
    ],
    category: "bags",
    price: 68,
    compareAt: 85,
    sku: "NL-BG-001",
    rating: 4.7,
    reviewCount: 212,
    histogram: [168, 31, 9, 3, 1],
    stock: "in",
    images: g(tote, "Field Tote"),
    variants: [{ name: "Color", options: ["Sand", "Olive"] }],
    highlights: [
      "18 oz organic cotton duck canvas",
      "Vegetable-tanned leather handles",
      "Interior slip pocket for phone and keys",
      "Double-layer base, bar-tacked seams",
      "Stands upright when empty",
    ],
    specs: {
      Materials: "18 oz cotton duck, vegetable-tanned leather",
      Dimensions: '16" W × 14" H × 6" D',
      Weight: "1.4 lb",
      Capacity: "22 L",
      Origin: "Sewn in Portland, Oregon",
    },
    care: "Spot clean with a damp cloth and mild soap. Do not machine wash. Condition leather handles once a season.",
    related: ["weekender-duffel", "camp-mug", "waxed-cap"],
    featured: true,
    reviews: [
      { name: "Maren K.", date: "2026-09-28", rating: 5, title: "My everything bag", body: "I've used it every Saturday at the farmers market since June. The canvas is stiff at first and then softens just right. Handles are already getting that honey color.", verified: true },
      { name: "Daniel O.", date: "2026-09-14", rating: 5, title: "Built like a tent", body: "Carried two growlers, a baguette and a wet towel home from the coast. No sagging, no stretched seams.", verified: true },
      { name: "Priya S.", date: "2026-08-30", rating: 4, title: "Great, wish it had a zip", body: "Love the size and the Sand color is perfect. I'd buy a version with a zip top for travel in a heartbeat.", verified: true },
      { name: "Tom W.", date: "2026-08-11", rating: 5, title: "Second one for my sister", body: "Bought Olive for myself last year and Sand for my sister now. Both still look new-ish, in the good way." },
      { name: "Hana L.", date: "2026-07-22", rating: 3, title: "Handles a bit short", body: "Quality is excellent but the handles are short for shoulder carry if you wear a thick coat. Fine by hand.", verified: true },
      { name: "Chris B.", date: "2026-07-03", rating: 5, title: "Worth the price", body: "Cheaper totes have come and gone. This one is clearly going to outlast them all.", verified: true },
    ],
  },
  {
    slug: "weekender-duffel",
    name: "Weekender Duffel",
    tagline: "Waxed canvas and brass for two nights away — or ten.",
    description: [
      "The Weekender is our answer to the overstuffed roller bag. It holds a weekend of clothes, a pair of boots and a book, and fits under most airline seats when you pack it smart.",
      "Waxed canvas sheds drizzle and develops creases and scuffs that tell where it's been. Solid brass hardware and a padded, removable shoulder strap make the walk from trailhead to cabin easy.",
      "A full-length YKK zipper opens wide, and an end pocket keeps shoes apart from everything else.",
    ],
    category: "bags",
    price: 128,
    sku: "NL-BG-002",
    rating: 4.8,
    reviewCount: 96,
    histogram: [80, 12, 3, 1, 0],
    stock: "in",
    images: g(duffel, "Weekender Duffel"),
    variants: [{ name: "Color", options: ["Charcoal", "Field Tan"] }],
    highlights: [
      "Water-resistant waxed canvas",
      "Solid brass hardware",
      "Removable padded shoulder strap",
      "Separate end pocket for shoes",
      "Full-length YKK zipper",
    ],
    specs: {
      Materials: "15 oz waxed cotton canvas, full-grain leather, brass",
      Dimensions: '22" W × 12" H × 11" D',
      Weight: "3.1 lb",
      Capacity: "45 L",
      Origin: "Sewn in Portland, Oregon",
    },
    care: "Brush off dirt when dry. Re-wax once a year with our bar wax or any paraffin-beeswax blend. Never machine wash.",
    related: ["field-tote", "repair-kit", "waxed-cap"],
    featured: true,
    reviews: [
      { name: "Elliot R.", date: "2026-10-02", rating: 5, title: "Lives in my trunk", body: "Packed for a three-day wedding with room to spare. The waxed finish already has a few character marks I love.", verified: true },
      { name: "Sofia M.", date: "2026-09-09", rating: 5, title: "Beautiful hardware", body: "The brass clips are heavy and smooth. It feels like something my grandfather would have owned.", verified: true },
      { name: "Grant H.", date: "2026-08-19", rating: 4, title: "Heavy but worth it", body: "It's not an ultralight bag, and it doesn't pretend to be. Shoulder strap pad makes a big difference.", verified: true },
      { name: "June P.", date: "2026-07-27", rating: 5, title: "Carry-on hero", body: "Fit in the overhead bin on a regional jet. Got two compliments at the gate." },
    ],
  },
  {
    slug: "trail-notebook",
    name: "Trail Notebook",
    tagline: "A pocket notebook for birds seen, miles walked and ideas half-formed.",
    description: [
      "Ninety-six pages of 100 gsm cream paper, dot-grid, bound in a kraft cover that softens to the shape of your back pocket.",
      "An elastic closure keeps loose pages and pressed leaves inside. The rounded corners won't dog-ear, and the paper takes pencil, gel and fountain pen without ghosting.",
      "Each notebook ships with a cedar pencil sized to tuck along the spine.",
    ],
    category: "notebooks",
    price: 18,
    compareAt: 22,
    sku: "NL-NB-001",
    rating: 4.6,
    reviewCount: 341,
    histogram: [251, 61, 18, 7, 4],
    stock: "in",
    images: g(notebook, "Trail Notebook"),
    variants: [{ name: "Ruling", options: ["Dot grid", "Blank", "Lined"] }],
    highlights: [
      "96 pages, 100 gsm cream paper",
      "Fountain-pen friendly, minimal ghosting",
      "Elastic closure, rounded corners",
      "Includes cedar pencil",
    ],
    specs: {
      Materials: "Recycled kraft cover, FSC paper",
      Dimensions: '3.5" × 5.5"',
      Weight: "2.6 oz",
      Pages: "96 (48 sheets)",
      Origin: "Printed in Oregon",
    },
    care: "Keep away from prolonged moisture. If it gets wet, dry flat under a heavy book.",
    related: ["surveyor-sketchbook", "brass-pocket-knife", "camp-mug"],
    featured: true,
    reviews: [
      { name: "Ava T.", date: "2026-10-10", rating: 5, title: "Finally, paper that takes ink", body: "My fountain pen doesn't bleed through at all. I've filled two already this summer.", verified: true },
      { name: "Marcus D.", date: "2026-09-21", rating: 4, title: "Great pocket size", body: "Fits my jeans. Elastic loosened a bit after a month but still works.", verified: true },
      { name: "Lena G.", date: "2026-09-02", rating: 5, title: "Bird log", body: "I keep one in my birding vest. The dot grid is perfect for quick sketches.", verified: true },
      { name: "Owen F.", date: "2026-08-15", rating: 3, title: "Pencil is tiny", body: "Notebook is lovely. The included pencil is cute but too short to actually use for long." },
      { name: "Ruth A.", date: "2026-07-30", rating: 5, title: "Bought a five-pack", body: "Using them as field journals for my kids. They hold up to being shoved in backpacks.", verified: true },
    ],
  },
  {
    slug: "surveyor-sketchbook",
    name: "Surveyor Sketchbook",
    tagline: "Clothbound, lay-flat, and ready for watercolor at the trailhead.",
    description: [
      "Inspired by old survey ledgers, this sketchbook is wrapped in forest-green bookcloth over rigid boards so you can draw standing up.",
      "The Smyth-sewn binding lays perfectly flat across a full spread. 150 gsm mixed-media paper handles light washes, graphite and ink.",
      "A back pocket holds loose maps, receipts or a pressed fern.",
    ],
    category: "notebooks",
    price: 32,
    sku: "NL-NB-002",
    rating: 4.5,
    reviewCount: 87,
    histogram: [60, 17, 6, 3, 1],
    stock: "low",
    stockLeft: 3,
    images: g(sketchbook, "Surveyor Sketchbook"),
    variants: [{ name: "Size", options: ['A5 (6×8")', 'Square (8×8")'] }],
    highlights: [
      "Smyth-sewn, lays flat",
      "150 gsm mixed-media paper",
      "Rigid boards for drawing on the go",
      "Back pocket for loose sheets",
    ],
    specs: {
      Materials: "Bookcloth over board, mixed-media paper",
      Dimensions: 'A5: 6" × 8" / Square: 8" × 8"',
      Weight: "13 oz",
      Pages: "120 (60 sheets)",
      Origin: "Bound in Oregon",
    },
    care: "Store flat. Allow wet media to dry fully before closing.",
    related: ["trail-notebook", "field-tote", "camp-mug"],
    reviews: [
      { name: "Iris N.", date: "2026-09-18", rating: 5, title: "Lays truly flat", body: "Painted a full panorama across the spread. No gutter issues at all.", verified: true },
      { name: "Ben C.", date: "2026-08-24", rating: 4, title: "Light washes only", body: "Buckles a bit with heavy watercolor, but for sketching and light washes it's perfect.", verified: true },
      { name: "Noor H.", date: "2026-08-03", rating: 5, title: "Gorgeous cloth", body: "The green cover is even nicer in person.", verified: true },
      { name: "Sam V.", date: "2026-07-12", rating: 4, title: "Solid sketchbook", body: "Wish there were a ribbon marker, otherwise excellent." },
    ],
  },
  {
    slug: "brass-pocket-knife",
    name: "Brass Pocket Knife",
    tagline: "A slipjoint for apples, twine and the occasional splinter.",
    description: [
      "A simple slipjoint with a 2.5\" Sandvik steel blade and a solid brass handle that will patina to a soft gold over the years.",
      "No locks, no clips, no fuss — just a reliable blade for camp chores, picnic cheese and opening boxes. Light enough to forget in your pocket.",
      "Each knife arrives sharpened and oiled, in a waxed-canvas slip.",
    ],
    category: "tools",
    price: 54,
    compareAt: 64,
    sku: "NL-TL-001",
    rating: 4.8,
    reviewCount: 158,
    histogram: [134, 17, 4, 2, 1],
    stock: "in",
    images: g(knife, "Brass Pocket Knife"),
    variants: [{ name: "Finish", options: ["Brass"] }],
    highlights: [
      '2.5" Sandvik 12C27 stainless blade',
      "Solid brass handle that patinas",
      "Non-locking slipjoint — legal in most places",
      "Ships sharpened, with canvas slip",
      "Lifetime sharpening service",
    ],
    specs: {
      Materials: "Sandvik 12C27 steel, solid brass",
      Dimensions: '3.4" closed / 5.9" open',
      Weight: "2.3 oz",
      Blade: '2.5" drop point',
      Origin: "Made in Spain, finished in Portland",
    },
    care: "Wipe dry after use. A drop of mineral oil on the pivot every few months. Polish brass if you prefer shine, or let it patina.",
    related: ["repair-kit", "camp-mug", "trail-notebook"],
    featured: true,
    reviews: [
      { name: "Walt E.", date: "2026-10-05", rating: 5, title: "Just a good knife", body: "Sharp out of the box. Patina started in a week. It's become my everyday pocket companion.", verified: true },
      { name: "Kira J.", date: "2026-09-12", rating: 5, title: "Gift for my dad", body: "He hasn't put it down. The canvas slip is a nice touch.", verified: true },
      { name: "Leo Z.", date: "2026-08-20", rating: 4, title: "Stiff at first", body: "Took a little effort to open the first week, smooth now.", verified: true },
      { name: "Anya P.", date: "2026-07-18", rating: 5, title: "Perfect size", body: "Small enough for city carry, useful enough for camping." },
      { name: "Rob T.", date: "2026-06-29", rating: 3, title: "Wish it locked", body: "Well made, but I'd prefer a locking blade for heavier tasks. That's on me.", verified: true },
    ],
  },
  {
    slug: "camp-mug",
    name: "Camp Mug",
    tagline: "Enamel steel for coffee at dawn and soup by the fire.",
    description: [
      "Our Camp Mug is enameled steel with a rolled charcoal rim — light, nearly indestructible, and just as happy on a camp stove as on your desk.",
      "It holds a generous 12 oz, stacks neatly, and gets the kind of small chips that make it look like it's been on a few trips.",
    ],
    category: "tools",
    price: 24,
    sku: "NL-TL-002",
    rating: 4.6,
    reviewCount: 404,
    histogram: [301, 72, 20, 7, 4],
    stock: "in",
    images: g(mug, "Camp Mug"),
    variants: [{ name: "Color", options: ["Cream", "Charcoal"] }],
    highlights: [
      "12 oz enameled steel",
      "Stovetop and campfire safe",
      "Rolled rim, stackable",
      "Dishwasher safe",
    ],
    specs: {
      Materials: "Enameled carbon steel",
      Dimensions: '3.5" Ø × 3.2" H',
      Weight: "7 oz",
      Capacity: "12 oz / 355 ml",
      Origin: "Made in Poland",
    },
    care: "Dishwasher safe. Avoid heating empty. Small chips are cosmetic and won't affect use.",
    related: ["trail-notebook", "brass-pocket-knife", "field-tote"],
    reviews: [
      { name: "Gwen S.", date: "2026-10-12", rating: 5, title: "Morning ritual", body: "Coffee tastes better out of this. I don't make the rules.", verified: true },
      { name: "Paolo R.", date: "2026-09-25", rating: 4, title: "Gets hot", body: "Metal rim gets warm with hot coffee, as expected. Otherwise perfect.", verified: true },
      { name: "Mina Y.", date: "2026-09-01", rating: 5, title: "Bought four", body: "Our whole camp set. They stack nicely in the bin.", verified: true },
      { name: "Jack L.", date: "2026-08-08", rating: 3, title: "Chipped on day two", body: "Dropped it on a rock. Small chip, still works. It's enamel, so fair." },
    ],
  },
  {
    slug: "waxed-cap",
    name: "Waxed Cap",
    tagline: "A six-panel cap that shrugs off drizzle and gets better with wear.",
    description: [
      "Made from the same waxed canvas as our Weekender, this low-profile six-panel cap keeps the sun and light rain off on long walks.",
      "A leather strap with a brass slide adjusts the fit. The unstructured crown molds to your head after a few wears.",
    ],
    category: "bags",
    price: 36,
    sku: "NL-AC-001",
    rating: 4.4,
    reviewCount: 73,
    histogram: [46, 17, 6, 3, 1],
    stock: "in",
    images: g(cap, "Waxed Cap"),
    variants: [
      { name: "Color", options: ["Olive", "Charcoal"] },
      { name: "Size", options: ["S/M", "L/XL"] },
    ],
    highlights: [
      "Water-resistant waxed cotton",
      "Leather strap with brass slide",
      "Unstructured, low-profile crown",
      "Cotton sweatband",
    ],
    specs: {
      Materials: "Waxed cotton, leather, brass",
      Dimensions: 'S/M fits 21.5–22.5", L/XL fits 22.75–24"',
      Weight: "3 oz",
      Origin: "Sewn in Portland, Oregon",
    },
    care: "Brush clean. Re-wax lightly as needed. Do not wash.",
    related: ["field-tote", "weekender-duffel", "camp-mug"],
    reviews: [
      { name: "Hugo B.", date: "2026-09-30", rating: 5, title: "Best cap I own", body: "Wore it in a full day of Oregon drizzle. Head stayed dry.", verified: true },
      { name: "Cleo F.", date: "2026-09-04", rating: 4, title: "Runs a bit small", body: "Size up if you're between sizes.", verified: true },
      { name: "Ivan K.", date: "2026-08-14", rating: 4, title: "Wax smell fades", body: "Smells like a tent at first. Gone in a week." },
      { name: "Dee M.", date: "2026-07-21", rating: 5, title: "Olive is lovely", body: "Goes with everything I own.", verified: true },
    ],
  },
  {
    slug: "repair-kit",
    name: "Repair Kit",
    tagline: "Needles, waxed thread and patches for mending on the trail.",
    description: [
      "Everything you need to fix a torn strap, a blown seam or a snagged tent fly, rolled up in a pocket-sized waxed-canvas wrap.",
      "Includes heavy-duty needles, a spool of waxed polyester thread, three iron-on and sew-on patches, safety pins and folding scissors. Small enough to live in every bag you own.",
    ],
    category: "tools",
    price: 29,
    sku: "NL-TL-003",
    rating: 4.7,
    reviewCount: 64,
    histogram: [50, 10, 3, 1, 0],
    stock: "low",
    stockLeft: 2,
    images: g(repair, "Repair Kit"),
    variants: [],
    highlights: [
      "Waxed-canvas roll with tie closure",
      "5 heavy-duty needles, 30 yd waxed thread",
      "3 canvas patches, 4 safety pins",
      "Folding stainless scissors",
    ],
    specs: {
      Materials: "Waxed canvas roll, stainless steel, polyester thread",
      Dimensions: '7" × 4" rolled',
      Weight: "4 oz",
      Origin: "Assembled in Portland, Oregon",
    },
    care: "Keep dry. Replace thread as needed — refills available.",
    related: ["weekender-duffel", "brass-pocket-knife", "field-tote"],
    reviews: [
      { name: "Noah G.", date: "2026-09-27", rating: 5, title: "Saved a trip", body: "Backpack strap tore on day one of a five-day hike. Fixed it in ten minutes.", verified: true },
      { name: "Bea W.", date: "2026-08-29", rating: 5, title: "Thoughtful kit", body: "Everything has a place. Nicer than it needs to be.", verified: true },
      { name: "Ray O.", date: "2026-08-02", rating: 4, title: "Scissors are small", body: "They work for thread, not much else.", verified: true },
      { name: "Tess C.", date: "2026-07-15", rating: 5, title: "Gift-worthy", body: "Gave three as stocking stuffers. Everyone loved them." },
    ],
  },
];

export const getProduct = (slug: string) => products.find((p) => p.slug === slug);

export const discountPct = (p: { price: number; compareAt?: number | undefined }) =>
  p.compareAt && p.compareAt > p.price ? Math.round((1 - p.price / p.compareAt) * 100) : 0;

export const formatUSD = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
