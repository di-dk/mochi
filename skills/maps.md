name: maps
description: Geocode places, find nearby POIs, get route distance/time/directions and timezones (free OSM data)

All calls are http_request GET, free, no key. Send headers {"User-Agent": "mochi-agent"} on EVERY call
(Nominatim and Overpass answer 403/406 without it).
1. Place -> coordinates: https://nominatim.openstreetmap.org/search?q=PLACE&format=json&limit=3&addressdetails=1
   Keep lat, lon, display_name and boundingbox (south, north, west, east).
2. Coordinates -> address: https://nominatim.openstreetmap.org/reverse?lat=LAT&lon=LON&format=json&addressdetails=1
3. Nearby places: geocode first (skip if the user gave lat/lon), then Overpass with the query URL-encoded:
   https://overpass-api.de/api/interpreter?data=[out:json][timeout:25];(node["amenity"="cafe"](around:1000,LAT,LON);
   way["amenity"="cafe"](around:1000,LAT,LON););out center 15;
   Radius in metres (500-2000 is usual). Most categories are amenity=...: restaurant, cafe, bar, hospital,
   pharmacy, atm, fuel, parking, bank, dentist, doctors, cinema, library. Others: shop=supermarket,
   tourism=hotel, tourism=museum, leisure=park, leisure=fitness_centre.
4. Places in a named area: same query with (SOUTH,WEST,NORTH,EAST) from step 1 instead of (around:...).
5. Distance and time: geocode both ends, then (note the order: LON,LAT)
   https://router.project-osrm.org/route/v1/driving/LON1,LAT1;LON2,LAT2?overview=false&steps=false
   Modes: driving (default), foot, bike. Read routes[0].distance (metres) and .duration (seconds).
6. Directions: the same URL with steps=true -> numbered list: manoeuvre, road name, distance.
7. Timezone: https://timeapi.io/api/timezone/coordinate?latitude=LAT&longitude=LON
   -> zone name, UTC offset, current local time.

RULES
- Nominatim: at most 1 request per second (use wait). Never run it in a loop over many places.
- Ambiguous name or a bare postcode: add city, state or country and search again.
- Overpass 502/504 means busy: wait 5 s and retry once, then try
  https://overpass.kumi.systems/api/interpreter once. Do not loop.
- OSRM coverage is best in Europe and North America. Say so if a route looks wrong.
- OSM opening hours are community-maintained. For "open now?" verify with web_search.
- Final answer: numbered list with name, address, distance, and cuisine/hours/phone/website when present.
  For routes: mode, distance in km, duration, then the steps.
