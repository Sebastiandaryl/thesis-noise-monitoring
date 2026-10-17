// Builds assets/ph-basemap.js: offline land shapes and city labels for the Philippines.
// Only needed to regenerate that file. Usage:
//   npm install topojson-client@3 pbf@3 world-atlas@2 all-the-cities@3
//   node build-ph-basemap.js node_modules/world-atlas/countries-10m.json node_modules/all-the-cities/cities.pbf ../assets/ph-basemap.js
const fs = require('fs'); const path = require('path');
const topo = require('topojson-client'); const Pbf = require('pbf');
const [atlasPath, citiesPath, outPath] = process.argv.slice(2);
const world = JSON.parse(fs.readFileSync(atlasPath, 'utf8'));
const countries = topo.feature(world, world.objects.countries).features;
const BBOX = [112, 0, 131, 23]; // lon/lat window around the Philippines
const KEEP = { '608': 'Philippines', '458': 'Malaysia', '360': 'Indonesia', '158': 'Taiwan', '096': 'Brunei' };
const r4 = v => Math.round(v * 1e4) / 1e4;
const land = [];
for (const f of countries) {
  if (!KEEP[f.id]) continue;
  const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
  for (const poly of polys) {
    const outer = poly[0];
    const lons = outer.map(p => p[0]), lats = outer.map(p => p[1]);
    if (Math.max(...lons) < BBOX[0] || Math.min(...lons) > BBOX[2] || Math.max(...lats) < BBOX[1] || Math.min(...lats) > BBOX[3]) continue;
    // [lat, lng] rings for Leaflet, dropping consecutive duplicates after rounding
    const rings = poly.map(ring => { const out = []; for (const [x, y] of ring) { const p = [r4(y), r4(x)]; const l = out[out.length - 1]; if (!l || l[0] !== p[0] || l[1] !== p[1]) out.push(p); } return out; }).filter(r => r.length > 3);
    if (rings.length) land.push({ c: f.id === '608' ? 1 : 0, r: rings });
  }
}
// Cities from GeoNames (all-the-cities), Philippines only
const pbf = new Pbf(fs.readFileSync(citiesPath)); let lastLat = 0, lastLon = 0; const cities = [];
while (pbf.pos < pbf.length) {
  const c = pbf.readMessage((tag, c, pbf) => {
    if (tag === 2) c.name = pbf.readString(); else if (tag === 3) c.country = pbf.readString();
    else if (tag === 4) c.alt = pbf.readString(); else if (tag === 5) c.muni = pbf.readString(); else if (tag === 6) c.sub = pbf.readString();
    else if (tag === 7) c.code = pbf.readString(); else if (tag === 8) c.admin = pbf.readString();
    else if (tag === 9) c.pop = pbf.readVarint();
    else if (tag === 10) { lastLon += pbf.readSVarint(); c.lon = lastLon / 1e5; }
    else if (tag === 11) { lastLat += pbf.readSVarint(); c.lat = lastLat / 1e5; }
    else if (tag === 1) pbf.readSVarint();
  }, { pop: 0 });
  if (c.country === 'PH' && (c.pop >= 60000 || c.code === 'PPLC' || c.code === 'PPLA')) cities.push([c.name, r4(c.lat), r4(c.lon), c.pop, c.code === 'PPLC' ? 1 : 0]);
}
// GeoNames lists some barangays and districts as cities; drop those and fix a few names.
const SKIP = new Set(['Budta', 'Malingao', 'Mansilingan', 'Santol', 'Mantampay', 'Libertad', 'Panalanoy', 'Guyong', 'Muricay', 'Bulaon', 'Pulong Santa Cruz', 'Binonga', 'NIA Valencia', 'Mariano', 'Tinongan', 'Ualog', 'Iligan']);
const RENAME = { 'Magugpo Poblacion': 'Tagum', 'Davao': 'Davao City', 'Zamboanga': 'Zamboanga City', 'Iloilo': 'Iloilo City' };
for (let i = cities.length - 1; i >= 0; i--) { if (SKIP.has(cities[i][0])) cities.splice(i, 1); else if (RENAME[cities[i][0]]) cities[i][0] = RENAME[cities[i][0]]; }
// Regional centers are labeled even when zoomed out to the whole country.
const REGIONAL = new Set(['Laoag', 'Tuguegarao', 'Baguio', 'Legaspi', 'Puerto Princesa', 'Iloilo City', 'Cebu City', 'Tacloban', 'Cagayan de Oro', 'Zamboanga City', 'Davao City', 'General Santos', 'Butuan']);
cities.forEach(c => { if (!c[4] && REGIONAL.has(c[0])) c[4] = 2; });
cities.sort((a, b) => b[3] - a[3]);
const js = `/* Offline basemap of the Philippines, used when online map tiles can't load.
   Land: Natural Earth 1:10m via world-atlas (public domain). Cities: GeoNames via all-the-cities (CC BY 4.0).
   Generated file. Format: land = [{ c: 1 for the Philippines, r: [[[lat, lng], ...], ...] }], cities = [[name, lat, lng, population, rank]] where rank is 1 for the capital, 2 for regional centers, else 0. */
const PH_BASEMAP = ${JSON.stringify({ land, cities })};
`;
fs.writeFileSync(outPath, js);
console.log('land polys', land.length, 'points', land.reduce((s, p) => s + p.r.reduce((a, r) => a + r.length, 0), 0), 'cities', cities.length, 'bytes', js.length);
console.log(cities.slice(0, 12).map(c => c[0] + ' ' + c[3]).join(', '));
