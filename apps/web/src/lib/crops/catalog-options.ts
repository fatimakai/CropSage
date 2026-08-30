export const CROP_CATALOG_OPTIONS = [
  { id: "upland_cotton", name: "Upland cotton" },
  { id: "corn_grain", name: "Corn grown for grain" },
  { id: "hard_red_winter_wheat", name: "Hard red winter wheat" },
  { id: "grain_sorghum", name: "Grain sorghum" },
  { id: "runner_peanut", name: "Runner-type peanut" },
  { id: "long_grain_rice", name: "Long-grain rice" },
  { id: "soybean", name: "Soybean" },
  { id: "grain_oats", name: "Grain oats" },
  { id: "oilseed_sunflower", name: "Oilseed sunflower" },
  { id: "sesame", name: "Sesame" },
  { id: "corn_silage", name: "Corn grown for silage" },
  { id: "forage_sorghum", name: "Forage sorghum" },
  { id: "sorghum_sudangrass", name: "Sorghum-sudangrass" },
  { id: "alfalfa_hay", name: "Alfalfa grown for hay" },
  { id: "bermudagrass_hay", name: "Bermudagrass grown for hay" },
  { id: "annual_ryegrass_forage", name: "Annual ryegrass grown for forage" },
  { id: "white_potato", name: "White potato" },
  { id: "sweet_potato", name: "Sweet potato" },
  { id: "seedless_watermelon", name: "Seedless watermelon" },
  { id: "dry_bulb_onion", name: "Dry-bulb onion" },
  { id: "fresh_market_cabbage", name: "Fresh-market cabbage" },
  { id: "fresh_market_spinach", name: "Fresh-market spinach" },
] as const;

export function cropCatalogName(cropId: string) {
  return CROP_CATALOG_OPTIONS.find((crop) => crop.id === cropId)?.name ?? null;
}
