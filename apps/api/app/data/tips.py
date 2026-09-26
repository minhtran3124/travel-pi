"""Local tips keyed by country (inherited by its cities) or city; IDs derive from list position, so append only."""

from app.data.cities import CITIES as _CITIES
from app.data.countries import COUNTRIES as _COUNTRIES
from app.enums import TipCategory as _TipCategory

COUNTRY_TIPS: dict[str, list[dict]] = {
    "Vietnam": [
        {
            "category": "money",
            "title": "Cash is king — carry small notes",
            "content": "The Vietnamese dong comes in large numbers; many small shops, markets and taxis are cash-only. Withdraw from bank ATMs and keep small denominations for street food and rides.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Use Grab instead of hailing taxis",
            "content": "The Grab app (cars and motorbikes) shows the price up front, so you avoid meter tampering. If taking a street taxi, stick to Vinasun or Mai Linh.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Watch bags on the street",
            "content": "Drive-by bag-snatching by motorbike happens in big cities. Keep phones and bags on the side away from the road and don't text while walking near traffic.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Street food is safe — pick busy stalls",
            "content": "Vietnamese street food is a highlight. Choose stalls with high turnover and locals queuing; that's the freshness signal. Drink bottled or filtered water.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Remove shoes and dress modestly at temples",
            "content": "Take shoes off when entering temples and homes, and cover shoulders and knees at religious sites. Use both hands when giving or receiving something from elders.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Buy a local eSIM or SIM on arrival",
            "content": "Viettel, Mobifone and Vinaphone sell cheap tourist data SIMs at airports. An eSIM bought before you fly works the moment you land.",
            "is_essential": False,
        },
        {
            "category": "language",
            "title": "A few words go a long way",
            "content": "'Xin chào' (hello), 'cảm ơn' (thank you). English is common in tourist areas but limited elsewhere — a translation app helps.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "The country has three climates",
            "content": "North, central and south Vietnam have different seasons. Broadly, Nov–Apr is drier in the south; the central coast is best Feb–Aug; avoid the Sep–Nov storm season on the central coast.",
            "is_essential": False,
        },
    ],
    "Thailand": [
        {
            "category": "transport",
            "title": "Grab and metered taxis over tuk-tuks",
            "content": "Tuk-tuks are fun but overcharge tourists and may detour to commission shops. Use Grab or insist on the meter ('meter, please') in taxis.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Carry cash, watch ATM fees",
            "content": "Thai ATMs charge a fixed foreign-card fee (~220 THB) per withdrawal, so take out larger amounts less often. Cash is needed for markets and street stalls.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Never disrespect the monarchy or Buddha images",
            "content": "Insulting the royal family is a serious crime. Don't point feet at people or Buddha images, don't touch anyone's head, and dress modestly at temples.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Common scams: gem shops and 'closed' temples",
            "content": "Ignore strangers who say a temple is closed and offer a tuk-tuk tour — it ends at a gem or tailor shop. Agree all prices before getting in.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Street food is excellent and cheap",
            "content": "Thailand's street food is world-class. Pick busy stalls, and tell vendors 'mai phet' if you want it less spicy. Drink bottled water.",
            "is_essential": False,
        },
        {
            "category": "health",
            "title": "Sun and heat are intense",
            "content": "Stay hydrated, use high-SPF sunscreen, and pace yourself midday. Mosquito repellent is worth carrying, especially in the rainy season.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Cheap tourist SIMs everywhere",
            "content": "AIS, TrueMove and dtac sell tourist data SIMs at airports and 7-Elevens for a few dollars. Coverage is good even on islands.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Cool season is Nov–Feb",
            "content": "Nov–Feb is dry and comfortable. Mar–May is very hot; Jun–Oct is the rainy season — showers are short but the Andaman coast can be rough.",
            "is_essential": False,
        },
    ],
    "Singapore": [
        {
            "category": "transport",
            "title": "The MRT covers almost everywhere",
            "content": "Singapore's MRT and bus network is clean, cheap and efficient. Tap any contactless bank card or buy an EZ-Link card — no need for taxis most of the time.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Cards accepted nearly everywhere",
            "content": "Contactless payment works almost universally, including hawker centres. Carry a little cash for the smallest stalls.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Very safe — but strict laws",
            "content": "Crime is very low. However fines are heavy: no eating or drinking on the MRT, no littering, no jaywalking, and chewing gum is restricted. Drug laws are extremely severe.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Eat at hawker centres",
            "content": "Hawker centres serve cheap, excellent food. To reserve a table locals leave a packet of tissues on it — respect that custom.",
            "is_essential": False,
        },
        {
            "category": "health",
            "title": "Tap water is safe to drink",
            "content": "Singapore tap water meets WHO standards — refill your bottle freely. The heat and humidity are constant, so hydrate often.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Hot and humid all year",
            "content": "Singapore is warm and humid year-round with no real seasons. Feb–Apr is slightly drier; Nov–Jan sees more rain but showers are brief.",
            "is_essential": False,
        },
    ],
    "Japan": [
        {
            "category": "money",
            "title": "Carry cash despite the tech image",
            "content": "Japan is still cash-heavy — many small restaurants, shrines and shops don't take cards. 7-Eleven ATMs reliably accept foreign cards.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Get an IC card; consider the JR Pass",
            "content": "A Suica or Pasmo IC card works on trains, buses and convenience stores nationwide. If doing long intercity travel, price-check the Japan Rail Pass first.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Quiet trains, no tipping, no eating while walking",
            "content": "Keep phone calls off trains, don't tip (it can offend), and avoid eating while walking. Bow slightly as a greeting and thanks.",
            "is_essential": True,
        },
        {
            "category": "culture",
            "title": "Carry your own rubbish",
            "content": "Public bins are rare. Carry a small bag for your trash until you find one — often near convenience stores or stations.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Rent pocket Wi-Fi or buy an eSIM",
            "content": "Free public Wi-Fi is patchy. A data eSIM or a rented pocket Wi-Fi router keeps maps and translation working everywhere.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Spring and autumn are peak",
            "content": "Late Mar–Apr (cherry blossom) and Oct–Nov (autumn leaves) are beautiful but busy. Summer is hot and humid; winter is great for snow and onsen.",
            "is_essential": False,
        },
    ],
    "Malaysia": [
        {
            "category": "money",
            "title": "Carry ringgit cash for small spots",
            "content": "Cards are widely accepted in malls and chains, but hawker stalls, markets and small towns are cash-only. Bank ATMs give the best rate; tell your bank you're travelling.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Grab is the default ride app",
            "content": "Grab works nationwide and shows prices up front, avoiding metered-taxi disputes. In KL the LRT/MRT and KTM trains are cheap and beat the traffic.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Watch for bag-snatching on motorbikes",
            "content": "Drive-by snatch theft happens in cities — walk on the side away from the road and keep bags cross-body. Otherwise Malaysia is generally safe and easy.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Dress modestly; respect Muslim customs",
            "content": "Malaysia is majority Muslim. Cover shoulders and knees at mosques (robes are usually lent), use your right hand for giving and eating, and avoid public displays of affection.",
            "is_essential": False,
        },
        {
            "category": "food",
            "title": "Hawker centres and kopitiams are the heart of the food scene",
            "content": "Nasi lemak, char kway teow and roti canai are cheap and superb at hawker stalls. Tap water should be boiled or filtered — stick to bottled.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Cheap prepaid SIMs at the airport",
            "content": "Maxis, Celcom and Digi sell tourist data SIMs at airport kiosks and convenience stores. Coverage is strong in cities and along the peninsula.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Two monsoons, so timing depends on the coast",
            "content": "The west coast and islands (Penang, Langkawi) are best Dec–Apr; the east coast (Perhentians, Tioman) is best Mar–Oct and largely shuts in the Nov–Feb monsoon.",
            "is_essential": False,
        },
    ],
    "Indonesia": [
        {
            "category": "money",
            "title": "Cash in rupiah, and use bank ATMs only",
            "content": "Outside hotels and big restaurants, Indonesia runs on cash. Use ATMs attached to banks (BCA, Mandiri) to avoid skimming, and check the machine before inserting your card.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Gojek and Grab for rides everywhere",
            "content": "Gojek and Grab offer cars and motorbike taxis at fixed app prices — far easier than haggling. On Bali, scooter rental is common but requires care and an international permit.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Volcanoes, currents and traffic are the real risks",
            "content": "Heed volcano and tsunami advisories, never swim against rip currents on south-coast beaches, and ride scooters cautiously. Petty theft happens but violent crime against tourists is rare.",
            "is_essential": True,
        },
        {
            "category": "health",
            "title": "Mind 'Bali belly' and mosquito-borne illness",
            "content": "Drink only bottled or filtered water and be cautious with ice and raw produce. Dengue is present, so use repellent, especially at dawn and dusk.",
            "is_essential": False,
        },
        {
            "category": "culture",
            "title": "Respect temple dress codes and offerings",
            "content": "A sarong and sash are required at Balinese temples (usually provided or rented). Don't step on the small daily canang sari offerings left on pavements and doorsteps.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Telkomsel has the widest coverage",
            "content": "Telkomsel reaches the most islands; an eSIM bought before arrival saves queuing. Wi-Fi is good in Bali and Jakarta but patchy in remote areas.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Dry season is roughly Apr–Oct",
            "content": "The dry season (Apr–Oct) is best across most of the archipelago, with Jul–Aug the peak. The Nov–Mar wet season brings heavy afternoon downpours.",
            "is_essential": False,
        },
    ],
    "Philippines": [
        {
            "category": "money",
            "title": "Carry peso cash, especially on islands",
            "content": "Cards work in Manila and Cebu malls, but island provinces, ferries and small eateries are cash-only and ATMs can be scarce or empty. Stock up before heading remote.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Domestic flights and ferries link the islands",
            "content": "With 7,000+ islands, budget airlines (Cebu Pacific, AirAsia) and ferries are how you get around — book ahead. In cities, use Grab; jeepneys are cheap but confusing for newcomers.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Check advisories for parts of Mindanao",
            "content": "Most of the country is welcoming and safe, but parts of western/central Mindanao and the Sulu Sea carry official travel warnings. Watch belongings in crowded Manila areas.",
            "is_essential": True,
        },
        {
            "category": "language",
            "title": "English is widely spoken",
            "content": "English is an official language and spoken almost everywhere, making the Philippines one of Asia's easiest countries to navigate for English speakers.",
            "is_essential": False,
        },
        {
            "category": "food",
            "title": "Try the regional specialities",
            "content": "Adobo, sinigang, lechon and halo-halo are staples; Cebu is famous for its roast pork. Drink bottled water and be a little cautious with street food.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Globe and Smart prepaid SIMs",
            "content": "Globe and Smart sell tourist SIMs at airport arrival halls. Coverage is reliable in cities but thin on remote islands — download offline maps.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Dry season Dec–May; typhoons Jun–Nov",
            "content": "Dec–Feb is dry and cooler; Mar–May is hot. The Jun–Nov typhoon season can disrupt ferries and flights, so build slack into island-hopping plans.",
            "is_essential": False,
        },
    ],
    "Cambodia": [
        {
            "category": "money",
            "title": "The US dollar is everyday currency",
            "content": "Prices are quoted and paid in US dollars; Cambodian riel is used as 'change' for amounts under a dollar. Bring clean, untorn small-denomination USD notes — damaged bills are refused.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Tuk-tuks and ride apps in towns",
            "content": "Tuk-tuks are the main way around Phnom Penh and Siem Reap; the PassApp and Grab apps give fixed fares and save haggling. Agree the price before any non-app ride.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Bag-snatching and unexploded ordnance",
            "content": "Drive-by phone and bag snatching is common in Phnom Penh — keep bags away from the road. In rural areas stick to marked paths; landmines and UXO remain in some regions.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Dress respectfully at Angkor and temples",
            "content": "Cover shoulders and knees to enter Angkor temples and pagodas — it is enforced at Angkor Wat. Return the 'sampeah' (palms-together) greeting and don't touch people's heads.",
            "is_essential": False,
        },
        {
            "category": "health",
            "title": "Heat, water and mosquitoes",
            "content": "It gets very hot — hydrate and pace temple visits for early morning. Drink bottled water and use repellent; dengue and malaria exist in rural areas.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Cheap, fast data SIMs",
            "content": "Cellcard, Smart and Metfone sell inexpensive data SIMs with generous allowances; coverage is good around the main towns and Angkor.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Cool dry season is Nov–Feb",
            "content": "Nov–Feb is dry and relatively cool — the best time for Angkor. Mar–May is punishingly hot; Jun–Oct is the wet season with lush scenery and fewer crowds.",
            "is_essential": False,
        },
    ],
    "Laos": [
        {
            "category": "money",
            "title": "Cash-heavy — carry kip, and some USD or baht",
            "content": "Laos runs almost entirely on cash; ATMs exist in towns but have low withdrawal limits and can be unreliable. The kip is the local currency, but USD and Thai baht are sometimes accepted.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Slow roads — the new fast train helps",
            "content": "Mountain roads make bus journeys long and winding; the China–Laos railway now links Vientiane, Vang Vieng and Luang Prabang quickly and cheaply, so book train seats ahead.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Stick to marked paths — UXO risk",
            "content": "Laos is heavily contaminated with unexploded ordnance from past wars. Never wander off established trails in rural areas, and don't touch unidentified metal objects.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Be calm, modest and quiet",
            "content": "Lao culture values composure — avoid raised voices and public anger. Dress modestly, especially at temples and the Luang Prabang alms-giving, which tourists should watch quietly and from a distance.",
            "is_essential": False,
        },
        {
            "category": "health",
            "title": "Water, food hygiene and mosquitoes",
            "content": "Drink bottled or filtered water and be careful with street food in smaller towns. Dengue and malaria occur in rural areas — use repellent and consider a net.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Unitel and Lao Telecom SIMs",
            "content": "Local SIMs from Unitel or Lao Telecom are cheap and cover the main towns. Connections slow down in the mountains, so download maps offline.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Best Nov–Feb; avoid the March haze",
            "content": "Nov–Feb is cool and dry — ideal for travel. Mar–Apr brings heat and slash-and-burn smoke haze in the north; May–Oct is the green, rainy season.",
            "is_essential": False,
        },
    ],
    "Myanmar": [
        {
            "category": "money",
            "title": "Bring pristine US dollars; cards rarely work",
            "content": "International cards and ATMs are largely unusable due to sanctions, so bring enough USD cash for your whole trip — crisp, unfolded, unmarked bills only, as worn notes are rejected.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Check current advisories before travelling",
            "content": "Myanmar has ongoing armed conflict and instability; many areas are off-limits and conditions change fast. Read your government's travel advisory carefully and avoid restricted regions.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Domestic flights over long road journeys",
            "content": "Roads are slow and some overland routes are closed to foreigners; domestic flights link Yangon, Mandalay and Bagan. Confirm which routes are currently permitted.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Strict temple etiquette",
            "content": "Remove shoes and socks completely before entering pagoda grounds, not just the buildings. Dress modestly covering shoulders and knees, and never point your feet at Buddha images.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Telenor/MPT SIMs, but expect outages",
            "content": "Local SIMs are cheap, but internet shutdowns and restrictions are common. A VPN installed in advance is widely used; don't rely on constant connectivity.",
            "is_essential": False,
        },
        {
            "category": "health",
            "title": "Limited medical care — be self-sufficient",
            "content": "Healthcare is basic outside Yangon; carry a stocked first-aid kit and any medication you need. Drink only bottled water and ensure travel insurance covers medical evacuation.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Cool dry season is Nov–Feb",
            "content": "Nov–Feb is the comfortable, dry window. Mar–May is extremely hot, and Jun–Oct is the rainy season with heavy monsoon downpours.",
            "is_essential": False,
        },
    ],
    "Brunei": [
        {
            "category": "money",
            "title": "Brunei dollar — Singapore dollars also accepted",
            "content": "The Brunei dollar is pegged 1:1 to the Singapore dollar, and SGD notes are accepted interchangeably. Cards work in larger shops and hotels, but carry cash for markets and small eateries.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Renting a car is easiest",
            "content": "Public transport is sparse and infrequent, and there is no widespread ride-hailing. Most visitors hire a car or rely on hotel transfers and taxis arranged in advance.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Very safe, but laws are strict",
            "content": "Crime is very low. However Brunei enforces sharia-influenced law: alcohol is banned for sale (limited personal import only), dress modestly, and behave conservatively in public.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Respect Islamic customs",
            "content": "Cover shoulders and knees, remove shoes at mosques, use your right hand, and don't eat or drink in public during Ramadan daylight hours. Public displays of affection are frowned upon.",
            "is_essential": False,
        },
        {
            "category": "culture",
            "title": "Friday is the day of rest",
            "content": "Many businesses and offices close midday Friday for prayers, and the weekend is Friday and Sunday. Plan visits to mosques and attractions around prayer times.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "DST and imagine SIMs",
            "content": "Prepaid SIMs from DST or imagine are available at the airport and in malls. Coverage is good across the populated coastal strip.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Hot and humid year-round",
            "content": "Brunei is tropical all year. The drier months are roughly Feb–Apr; Oct–Jan sees the heaviest rain, though showers are usually short.",
            "is_essential": False,
        },
    ],
    "Timor-Leste": [
        {
            "category": "money",
            "title": "US dollars are the official currency",
            "content": "Timor-Leste uses the US dollar; small local centavo coins are used for change. ATMs are limited to Dili and unreliable, so bring enough clean USD cash, especially for travel outside the capital.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Rough roads — 4WD and microlets",
            "content": "Roads outside Dili are poor and journeys are slow; a 4WD with a driver is the practical choice for the districts. In Dili, shared 'microlet' minibuses and taxis get you around cheaply.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Generally calm, but come prepared",
            "content": "Timor-Leste is mostly peaceful, though occasional unrest occurs around political events. Infrastructure and emergency services are limited — travel with insurance and a self-sufficient mindset.",
            "is_essential": True,
        },
        {
            "category": "health",
            "title": "Malaria, dengue and limited care",
            "content": "Malaria and dengue are present — use repellent and consider prophylaxis. Medical facilities are very basic; carry a first-aid kit and ensure insurance covers evacuation to Darwin or Bali.",
            "is_essential": False,
        },
        {
            "category": "language",
            "title": "Tetum and Portuguese, some Indonesian",
            "content": "Tetum and Portuguese are official; many people also speak Indonesian, and English is limited outside Dili. A few Tetum phrases are warmly received.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Telkomcel and Telemor SIMs",
            "content": "Local SIMs from Telkomcel or Telemor are cheap but data is slow and patchy outside Dili. Download offline maps before heading into the districts.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Dry season is May–Nov",
            "content": "May–Nov is dry, with the best road conditions and diving visibility. The Dec–Apr wet season can wash out mountain roads.",
            "is_essential": False,
        },
    ],
    "Hong Kong": [
        {
            "category": "transport",
            "title": "Get an Octopus card for everything",
            "content": "The MTR metro is fast, cheap and reaches almost everywhere. An Octopus card (or contactless bank card) works on the MTR, buses, trams, the Star Ferry and in convenience stores.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Hong Kong dollars; cards widely accepted",
            "content": "Cards and Octopus are taken nearly everywhere, but keep some HKD cash for street markets, dai pai dong food stalls and older taxis. ATMs are plentiful.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Very safe — usual big-city caution",
            "content": "Hong Kong has low crime; just watch for pickpockets in crowded markets and on the MTR. Check for any current advisories before travelling.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Dim sum, cha chaan teng and street food",
            "content": "Yum cha (dim sum) is a must, and cha chaan teng diners serve cheap local classics. Tap water is treated and considered safe, though many locals still boil it.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Easy SIMs and widespread Wi-Fi",
            "content": "Prepaid data SIMs are sold cheaply at the airport and in 7-Elevens, and free Wi-Fi is common in malls, the MTR and public spaces.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Stand right on escalators; queue properly",
            "content": "Stand on the right of escalators so others can pass on the left, and queue orderly for transport and lifts. Eating is not allowed on the MTR.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Autumn (Oct–Dec) is the sweet spot",
            "content": "Oct–early Dec is dry, sunny and comfortable. Summer is hot, humid and the typhoon season; Jan–Feb can be cool and grey.",
            "is_essential": False,
        },
    ],
    "South Korea": [
        {
            "category": "transport",
            "title": "T-money card for seamless transit",
            "content": "Buy a rechargeable T-money card at any convenience store — it works on subways, buses and taxis nationwide. Seoul's subway is extensive, signed in English and very cheap.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Cards everywhere, but carry some won",
            "content": "South Korea is highly card-friendly, even for tiny purchases. Still keep some cash for traditional markets and small rural vendors; use Global ATMs (at banks, 7-Eleven) for foreign cards.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Very safe, day and night",
            "content": "Crime against tourists is very low and it's safe to walk at night. Take normal precautions in nightlife districts, and note that fire/medical emergencies are 119, police 112.",
            "is_essential": True,
        },
        {
            "category": "connectivity",
            "title": "Fast data SIMs and ubiquitous Wi-Fi",
            "content": "Korea has some of the world's fastest internet; pick up a tourist SIM or eSIM (KT, SKT, LG U+) at the airport. Free Wi-Fi is everywhere, including the subway.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Use two hands; mind your shoes and elders",
            "content": "Give and receive money and gifts with two hands, remove shoes when entering homes and many traditional restaurants, and let elders sit and eat first.",
            "is_essential": False,
        },
        {
            "category": "food",
            "title": "Banchan, BBQ and spicy staples",
            "content": "Meals come with free refillable banchan side dishes. Korean BBQ, bibimbap and stews are everywhere; tap water is safe and restaurants provide free filtered water.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Spring and autumn are ideal",
            "content": "Apr–Jun (blossoms) and Sep–Nov (autumn foliage) are mild and beautiful. Summer is hot, humid and includes a rainy season; winter is cold but good for skiing.",
            "is_essential": False,
        },
    ],
    # BEGIN gh-237 country-tips
    "China": [
        {
            "category": "money",
            "title": "Use mobile payments, not foreign cards",
            "content": "Visa and MasterCard are rarely accepted in China. Set up WeChat Pay and Alipay, which support linking foreign bank cards for essential payments.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Download Amap or Baidu Maps before arrival",
            "content": "Google Maps doesn't work in China. Download Amap or Baidu Maps before you arrive — essential for navigation on foot, by car, or via public transport.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Spring and autumn offer ideal weather",
            "content": "North China experiences intensely hot summers and bitterly cold winters. Spring and autumn provide pleasant weather across most regions.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Avoid drugs and political activity",
            "content": "Avoid drugs and political discussions. As long as you behave appropriately, you shouldn't encounter problems during your visit.",
            "is_essential": True,
        },
        {
            "category": "connectivity",
            "title": "Install a VPN before arriving",
            "content": "Set up a VPN before you arrive, as many foreign sites are blocked; as of September 2024 users reported Mullvad and Astrill as reliable, but check current reviews.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Chopstick etiquette: never place upright",
            "content": "Never place chopsticks upright in a bowl — it resembles funeral rites. Avoid passing food chopstick-to-chopstick or drumming bowls.",
            "is_essential": False,
        },
    ],
    "Taiwan": [
        {
            "category": "money",
            "title": "Currency limits: under NT$100,000 cash",
            "content": "Taiwanese currency is fully convertible. You can only take under NT$100,000 cash into or out of the island to prevent money laundering.",
            "is_essential": False,
        },
        {
            "category": "transport",
            "title": "Use the excellent train system",
            "content": "Taiwan's train system is excellent with stops in all major cities, usually located centrally. It bypasses crowded highways and serves as a convenient transport hub.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Visit October to December",
            "content": "The best time to visit Taiwan is October to December with ideal weather. Spring is nice but rainier; avoid June to September typhoon season.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Most taxi drivers are honest",
            "content": "Taiwan taxi drivers are generally more honest than in many countries. Avoid overzealous drivers congregating at train station exits.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Water fountains are everywhere",
            "content": "Water dispensers and fountains are ubiquitous throughout Taiwan. Bring a reusable bottle and refill it free — many shops offer discounts for using your own.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Chopsticks: never place upright",
            "content": "Never stick chopsticks upright in rice — it resembles funeral rites. Food is shared family-style; avoid spearing or moving items with chopsticks.",
            "is_essential": False,
        },
    ],
    "France": [
        {
            "category": "money",
            "title": "Visa and MasterCard work widely",
            "content": "Visa and MasterCard are accepted almost everywhere in France. American Express is accepted only in high-end shops. ATMs offer the best exchange rates.",
            "is_essential": False,
        },
        {
            "category": "transport",
            "title": "Use TGV high-speed trains",
            "content": "TGV (Trains à Grande Vitesse) high-speed trains connect all major cities reliably. Reservations are mandatory. Regional trains are slower but scenic.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Spring and autumn are ideal",
            "content": "Spring and autumn bring decent weather across most of France and a quieter tourist season; avoid August, when much of the country heads south on holiday.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Start conversations in French",
            "content": "Always greet locals in French first. Assuming a foreign language will be understood is considered rude. Even clumsy attempts at French are appreciated.",
            "is_essential": True,
        },
        {
            "category": "connectivity",
            "title": "Wi-Fi available in trendy cafés",
            "content": "Wi-Fi is available in trendy cafés, often marked with an @ symbol on the door. Carrefour supermarkets also offer free Wi-Fi.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Greet staff, wait to be seated",
            "content": "Greet restaurant staff with 'bonjour' or 'bonsoir' when entering. Wait at the door to be shown to your table rather than seating yourself.",
            "is_essential": False,
        },
    ],
    "United Kingdom": [
        {
            "category": "money",
            "title": "Carry coins for small transactions",
            "content": "The UK still uses cash widely. Coins range from 1p to £2 denominations. Many buses and some services only accept coins or cards, not banknotes.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Use trains for inter-city travel",
            "content": "Trains are Britain's best option for inter-city travel — fast, comfortable, and convenient. Britain invented trains and maintains an extensive network.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Spring and autumn best for regions",
            "content": "Warm, damp summers and mild winters make the UK good for outdoor activities all year; in spring and autumn the north can be much cooler than the south.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Generally very safe to visit",
            "content": "The UK is generally safe for visitors. Follow standard European travel advice and exercise basic common sense.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "4G and 5G nearly universal",
            "content": "5G is available from all providers across most of the UK, and 4G covers nearly the whole population, though signal can be patchy in hilly areas.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Rest wrist, not elbows, while dining",
            "content": "Hold fork in left hand, knife in right. Rest only your wrist on the table, not elbows. This standard applies at upscale establishments.",
            "is_essential": False,
        },
    ],
    "Portugal": [
        {
            "category": "money",
            "title": "Use ATMs for best exchange rates",
            "content": "ATMs (Multibanco or ATM Express) accepting international cards are found everywhere without extra machine fees. They offer the best exchange rates.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Book Alfa-Pendular trains ahead",
            "content": "Alfa-Pendular high-speed trains run up to 220 km/h between major cities. Book at least 5 days in advance for a generous 40% discount.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Summer brings warm, sunny days",
            "content": "Portugal is one of the warmest and sunniest countries in Europe; spring and summer are usually sunny, with the hottest days in July and August.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Relatively safe, use common sense",
            "content": "Portugal is relatively safe with no terrorism or widespread violent crime. Use basic precautions in Lisbon and Porto where pickpockets target tourists.",
            "is_essential": True,
        },
        {
            "category": "connectivity",
            "title": "Tap water is safe to drink",
            "content": "Portugal's water sources are perfectly safe to drink directly from the tap. Bottled or spring water is available if you prefer.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Soup is the traditional first course",
            "content": "Soup is an essential first course in Portuguese meals. Caldo verde — made with kale, potatoes, and spiced sausage — is a popular Minho specialty.",
            "is_essential": False,
        },
    ],
    "Italy": [
        {
            "category": "money",
            "title": "Use bank-owned ATMs for fee-free withdrawals",
            "content": "ATMs owned directly by Italian banks like BNL and the postal service Postamat machines don't charge foreign visitors a withdrawal fee, though your own bank may still levy a charge.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Trenitalia offers reliable train travel",
            "content": "Italy's trains are affordable and dependable, with Trenitalia running both high-speed and regional services nationwide, plus Italo offering additional options on major routes.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Visit in spring or fall, avoid July–August",
            "content": "July and August are the hottest months across most of Italy, so spring and autumn are the most comfortable times to travel.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Italy is generally safe for tourists",
            "content": "Crime against travelers is rare; most serious incidents are tied to internal politics rather than targeting tourists or foreigners.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "4G coverage is widespread nationwide",
            "content": "All major Italian carriers provide 4G connectivity, ensuring reliable mobile internet access in cities and most rural areas.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Cappuccino is a breakfast drink only",
            "content": "Italians consider ordering cappuccino after breakfast socially awkward; ask for a macchiato (espresso with milk) if you want milky coffee after 11:00 AM.",
            "is_essential": False,
        },
    ],
    "Australia": [
        {
            "category": "money",
            "title": "Card rounding differs from cash transactions",
            "content": "If paying with cash, amounts are rounded to the nearest five cents; credit card payments charge the exact total. This is a quirk of Australian retail, not a fee.",
            "is_essential": False,
        },
        {
            "category": "transport",
            "title": "Domestic flights depart almost like a bus service",
            "content": "On busy routes like Melbourne–Sydney–Brisbane, flights leave every 15 minutes during the day, making air travel the fastest and most convenient way to cross Australia's vast distances.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Year-round sunshine across most of Australia",
            "content": "Most of Australia receives more than 3,000 hours of sunshine annually, making it reliably sunny regardless of season—though the north is tropical and the south is temperate.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Avoid driving at dusk or after dark",
            "content": "Wildlife collisions with vehicles spike dramatically during dusk and nighttime driving, so plan trips to end before dark and take extra caution if night driving is unavoidable.",
            "is_essential": True,
        },
        {
            "category": "connectivity",
            "title": "Free WiFi available at most accommodations",
            "content": "Nearly all hotels, hostels, cafés, restaurants, and shopping centers offer complimentary WiFi, plus some trains and ferries provide internet access.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Use first names with everyone",
            "content": "Australians are informal across all contexts; it's normal and expected to address people by their first name even if they're much older or senior to you.",
            "is_essential": False,
        },
    ],
    "United Arab Emirates": [
        {
            "category": "money",
            "title": "Cards work everywhere; specific ATMs are free",
            "content": "Visa, MasterCard, and Maestro are universally accepted. For ATM withdrawals, banks like Emirates NBD, HSBC, and ADIB don't charge foreign visitors, though some banks do.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Short distances mean quick travel between emirates",
            "content": "The UAE is compact; excellent highways connect all seven emirates in under two hours, with Dubai and Abu Dhabi just 90 minutes apart, making regional exploration straightforward.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Visit October through March for pleasant weather",
            "content": "Visit between late October and mid-March, when the weather is pleasant; pack a light jacket for winter evenings, and more for the desert, which can get freezing cold.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Low crime, but drive defensively",
            "content": "The UAE ranks among the world's safest countries for crime, but road accidents are common—exercise extreme caution when driving or crossing streets.",
            "is_essential": True,
        },
        {
            "category": "connectivity",
            "title": "VoIP apps are blocked; use corporate tools instead",
            "content": "WhatsApp, Facebook Messenger, and Snapchat voice/video calls don't work in the UAE. Use Zoom or Microsoft Teams for video communication, or rely on local SIM messaging.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Always use your right hand for business cards",
            "content": "In Emirati culture, giving or receiving with the left hand is considered deeply disrespectful. Use only your right hand when exchanging business cards or eating.",
            "is_essential": False,
        },
    ],
    "Turkey": [
        {
            "category": "money",
            "title": "Tip in cash, not on the card",
            "content": "Tipping isn't obligatory, but about 10% is common in restaurants; tips can't be added to a card bill, so leave cash, and skip it where a service or cover charge applies.",
            "is_essential": False,
        },
        {
            "category": "transport",
            "title": "Buses depart frequently with complimentary service",
            "content": "Turkish intercity buses are excellent; from any major bus station (Otogar) you can find departures within an hour to almost anywhere. On-board staff serve free drinks and snacks, with rest stops every 2–3 hours.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Coastal areas are mild; inland regions get bitter cold",
            "content": "Southern and western coasts are Mediterranean and pleasant year-round. The north is rainy with temperate rainforests, while eastern interior regions experience extreme cold (approaching -40°C in winter).",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Security checkpoints are routine, not a warning sign",
            "content": "Museums, hotels, shopping centers, and metro stations have airport-style security checkpoints. This is standard procedure in Turkey and does not indicate danger.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Buy a tourist SIM from Turkcell, Vodafone, or Türk Telekom",
            "content": "Every mobile operator — Turkcell, Vodafone and Türk Telekom — sells tourist SIM cards and data packages; bring your passport to buy one.",
            "is_essential": False,
        },
        {
            "category": "etiquette",
            "title": "Leave 10% tip in cash if satisfied with service",
            "content": "Tipping 10% at restaurants is customary if you're happy with the meal and service. Tips cannot be added to credit cards—pay in cash or coins.",
            "is_essential": False,
        },
    ],
    "United States": [
        {
            "category": "money",
            "title": "Carry cash and small bills for tips",
            "content": "Foreign credit and debit cards are accepted at most places, but keep several $1 and $5 bills on hand for cases where cards aren't accepted or when you need to leave a tip.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Major carriers offer competitive domestic fares",
            "content": "Domestic flights often cost more than similar distances in Europe or Asia; between Boston, New York and Washington, Amtrak's Acela and Northeast Regional trains are a practical alternative.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Spring and fall offer mild weather nationwide",
            "content": "October through April brings pleasant temperatures in the South; summer is hot and humid with afternoon thunderstorms in many regions. Winter brings snow to northern areas and icy roads through the Rockies.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Generally safe for tourists; exercise normal caution",
            "content": "The U.S. is a safe destination for most travelers. Avoid isolated areas at night, keep valuables secure, and follow local guidance in unfamiliar neighborhoods.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "WiFi hotspots and mobile networks cover most areas",
            "content": "Travelers can expect WiFi and 4G cellular coverage in cities, suburbs, and along highways. Remote areas may require satellite internet, which is expensive and best reserved for emergencies.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Tipping is widely expected and essential",
            "content": "Tipping 15–20% at restaurants, bars, taxis, and hotels is a cultural norm and often a server's primary income. Always carry small bills to tip in cash.",
            "is_essential": False,
        },
    ],
    # END gh-237 country-tips
}

CITY_TIPS: dict[str, list[dict]] = {
    "Hanoi": [
        {
            "category": "transport",
            "title": "Crossing the road: walk slow and steady",
            "content": "Traffic won't stop for you, but it will flow around you. Step out at a steady, predictable pace — don't run or freeze — and motorbikes will avoid you.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Old Quarter 'train street' has restricted access",
            "content": "The famous train-track cafés are periodically closed by authorities for safety. Go with a café that has current access and never linger on the tracks.",
            "is_essential": False,
        },
        {
            "category": "food",
            "title": "Try egg coffee — a Hanoi original",
            "content": "Cà phê trứng (egg coffee) was invented here. Pair it with a bowl of bún chả, the city's signature grilled-pork noodle dish.",
            "is_essential": False,
        },
    ],
    "Ho Chi Minh City": [
        {
            "category": "safety",
            "title": "Phone-snatching hotspots in District 1",
            "content": "Drive-by snatching is common around Bui Vien and busy District 1 streets. Don't hold your phone out near the kerb; use a cross-body bag.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Grab bikes beat the traffic",
            "content": "For short hops, a GrabBike is faster and cheaper than a car in HCMC's dense traffic. Helmets are provided.",
            "is_essential": False,
        },
    ],
    "Bangkok": [
        {
            "category": "transport",
            "title": "BTS Skytrain and river boats skip the gridlock",
            "content": "Bangkok traffic is severe. The BTS Skytrain, MRT and Chao Phraya express boats are the fastest way across the city.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "The Grand Palace is open — ignore 'closed today'",
            "content": "Anyone outside saying the Grand Palace or a temple is closed for a holiday is running the gem-shop scam. Walk to the official entrance and check yourself.",
            "is_essential": True,
        },
    ],
    "Kuala Lumpur": [
        {
            "category": "transport",
            "title": "Don't confuse KL Sentral with KLCC",
            "content": "KL Sentral is the main transport hub; KLCC is the Petronas Towers area. The free GOKL city bus loops the centre, and the LRT/MRT spares you KL's heavy traffic.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Bukit Bintang touts and inflated bills",
            "content": "Around Bukit Bintang and Jalan Alor, ignore touts pushing clubs and check menu prices before ordering at seafood stalls — some bill 'market price' at tourist rates.",
            "is_essential": False,
        },
    ],
    "Bali": [
        {
            "category": "transport",
            "title": "Book Grab/Gojek away from the rank",
            "content": "Local taxi 'mafias' bar app rides at some beaches and tourist spots — order a Grab or Gojek a short walk away, or use the metered Blue Bird taxi.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Use bank ATMs, watch the money changers",
            "content": "Use ATMs at bank branches and decline machines offering odd rates. Authorised money changers should count in front of you — walk away from any that rush or distract you.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Monkeys at Ubud and Uluwatu grab loose items",
            "content": "At the Ubud Monkey Forest and Uluwatu temple, monkeys snatch sunglasses, phones and bags. Keep valuables zipped away and don't tease or feed them.",
            "is_essential": False,
        },
    ],
    "Seoul": [
        {
            "category": "transport",
            "title": "Subway exit numbers are your map",
            "content": "Seoul's subway exits are numbered and signed precisely — directions are usually given as 'Exit 6'. Use Naver Map or KakaoMap, as Google Maps walking/transit directions are limited in Korea.",
            "is_essential": True,
        },
        {
            "category": "culture",
            "title": "Free hanbok = free palace entry",
            "content": "Wearing a hanbok (rentable near Gyeongbokgung) gets you free admission to the major palaces. Many shops near the gates rent them by the hour.",
            "is_essential": False,
        },
    ],
    # BEGIN gh-237 city-tips
    "Shanghai": [
        {
            "category": "transport",
            "title": "Use Shanghai's extensive metro system",
            "content": "Shanghai's public transport network is anchored by one of the world's most extensive metro systems, clean, fast, and affordable.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Get a Shanghai Jiaotong Card for transit",
            "content": "The Jiaotong transit card lets you change lines at certain stations without needing another ticket, on top of the usual bus and metro discounts.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Shanghai is very safe for solo travelers",
            "content": "Violent crime is rare in Shanghai and it is generally not a problem for women to roam the streets alone.",
            "is_essential": True,
        },
    ],
    "Beijing": [
        {
            "category": "transport",
            "title": "Use Beijing's extensive subway system",
            "content": "The Beijing Subway has many lines and stations covering the city with affordable fares.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Beijing is safe but watch for tourist scams",
            "content": "Violent crime is rare but tourists should be cautious of taxi scams.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Try Peking duck at specialist restaurants",
            "content": "A famous specialty served with pancakes, plum sauce, scallions and cucumbers.",
            "is_essential": False,
        },
    ],
    "Guangzhou": [
        {
            "category": "transport",
            "title": "Buy a Yang Cheng Tong card for transit",
            "content": "A stored value card that works on metro, buses and taxis with discount rates.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Experience authentic Cantonese cuisine",
            "content": "Guangzhou is famous for Cantonese food, dim sum and fresh seafood.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Guangzhou is generally safe for tourists",
            "content": "Violent crime is rare and the crime rate compares favorably with Western cities.",
            "is_essential": True,
        },
    ],
    "Paris": [
        {
            "category": "transport",
            "title": "Paris has an excellent metro",
            "content": "The Métro and RER move millions of people daily at affordable rates with frequent service.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Book Restaurants Well Ahead",
            "content": "Trendy Paris restaurants often need reservations weeks or months ahead; a lunch reservation is usually easier and cheaper to get.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Avoid crowded transit areas",
            "content": "The metro and RER are popular targets for pickpockets, so stay alert on crowded trains and platforms.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Enjoy local cafes",
            "content": "Traditional bistros with sidewalk terraces offer simple, reasonably priced meat-centred meals across the city.",
            "is_essential": False,
        },
    ],
    "London": [
        {
            "category": "transport",
            "title": "Use public transport effectively",
            "content": "A contactless bank card is often the most convenient way to pay for buses, the Tube and trains, priced the same as an Oyster card.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Book Around Major Events",
            "content": "Hotel prices spike close to major sporting tournaments like Wimbledon or big football fixtures, so plan or book well ahead around such events.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Watch Your Belongings",
            "content": "Keep normal precautions for your belongings: begging, drug abuse and phone-snatching theft occur in London like in any big city.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Diverse food options",
            "content": "The city offers a rich multicultural dining scene with cuisines from around the world.",
            "is_essential": False,
        },
    ],
    "Lisbon": [
        {
            "category": "transport",
            "title": "Use public transport",
            "content": "The integrated Navegante card provides seamless access across metro, buses, and trams throughout the city.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Try fresh seafood",
            "content": "Head to the 'seafood strip' on Rua das Portas de Santo Antão, near Praça dos Restauradores, for fresh seafood restaurants.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Lisbon Has Good Budget Hostels",
            "content": "Lisbon has clean, active hostels citywide, with prices in the historic center starting around 30 euros and cheaper further out.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Skip Costly Tourist Buses",
            "content": "Instead of a costly tourist bus, ride tram line 28 through the Old Town from Graca down to Alfama and Baixa.",
            "is_essential": False,
        },
    ],
    "Rome": [
        {
            "category": "transport",
            "title": "Walk in historic center",
            "content": "Medieval streets have uneven surfaces, so wear supportive shoes for comfortable exploration.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Protect valuables on transit",
            "content": "Exercise caution on crowded metro trains where thieves operate in organized groups.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Plan travel wisely",
            "content": "Check accommodation pricing for your specific dates to find the best rates.",
            "is_essential": False,
        },
        {
            "category": "food",
            "title": "Avoid Restaurant Tourist Traps",
            "content": "Guidebook-recommended restaurants can be inflated 'tourist traps'; look for places in residential areas away from major sights instead.",
            "is_essential": True,
        },
    ],
    "Osaka": [
        {
            "category": "transport",
            "title": "Use the Osaka Metro efficiently",
            "content": "The Osaka Metro is Japan's second-most extensive metro network after Tokyo. Use the red Midosuji Line as the main artery connecting major attractions and districts. Keep your ticket to exit.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Try kuidaore, eat yourself into ruin",
            "content": "Osaka is famous for its food culture. Experience authentic local cuisine at Dōtonbori with its countless restaurants serving okonomiyaki, takoyaki, and local specialties.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Osaka is remarkably safe for a major city",
            "content": "While Osaka has a reputation for crime among Japanese residents, it remains extremely safe compared to Western cities of similar size. Avoid certain southern areas at night.",
            "is_essential": False,
        },
        {
            "category": "transport",
            "title": "Stand right on escalators to let others pass",
            "content": "When using escalators, stand to the right to allow people in a hurry to pass on the left. This is the local custom in Osaka.",
            "is_essential": False,
        },
    ],
    "Kyoto": [
        {
            "category": "transport",
            "title": "Purchase transit passes for Kyoto travel",
            "content": "Use Kyoto Sightseeing Cards (¥900 one-day, ¥1700 two-day) for unlimited subway and bus travel. Or purchase ICOCA card (¥2000) usable across Kansai region.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Experience kaiseki and matcha specialties",
            "content": "Kyoto is considered the spiritual home of kaiseki fine dining. Kyoto and nearby Uji are famous for matcha green tea and matcha-flavored treats.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Spring and autumn offer best conditions",
            "content": "Spring cherry blossoms and autumn colors are beautiful but crowded. Consider shoulder seasons for fewer tourists and pleasant weather.",
            "is_essential": False,
        },
    ],
    "Fukuoka": [
        {
            "category": "food",
            "title": "Tonkotsu ramen is Hakata specialty",
            "content": "Hakata is famous for tonkotsu ramen with thick pork bone broth simmered for hours.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Hakata Line to airport",
            "content": "Hakata station connects directly to Fukuoka International Airport.",
            "is_essential": True,
        },
        {
            "category": "connectivity",
            "title": "Tenjin underground shopping center",
            "content": "Tenjin area is compact. Underground shopping center runs under Watanabe Street.",
            "is_essential": False,
        },
        {
            "category": "transport",
            "title": "Tunnel shelters from rain and cold",
            "content": "A passenger tunnel links Hakata and Gion subway stations, handy during Fukuoka's frequent summer rains and cold winter winds.",
            "is_essential": False,
        },
    ],
    "Sapporo": [
        {
            "category": "food",
            "title": "Try Sapporo soup curry",
            "content": "Sapporo soup curry has become increasingly famous alongside the city's signature miso ramen.",
            "is_essential": True,
        },
        {
            "category": "transport",
            "title": "Subway and bus network",
            "content": "Sapporo has a well-developed subway system connecting major attractions and neighborhoods.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Miso ramen local specialty",
            "content": "Sapporo is famous for its miso-based ramen with a rich pork bone broth.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Grid system for navigation",
            "content": "Most unusually for a Japanese city, Sapporo is logically organized thanks to its strict grid system.",
            "is_essential": False,
        },
    ],
    "Busan": [
        {
            "category": "transport",
            "title": "Use a T-money Card for Transit",
            "content": "Purchase a T-money or Cashbee card at convenience stores for seamless travel across metro, buses, and taxis with automatic discounts.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Busan is Very Safe to Explore",
            "content": "Busan is as safe as most places in South Korea. Avoid areas around Busan Station late at night, and be cautious of occasional drunk patrons on late-night metro rides.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Try Dong-nae Pajeon Locally",
            "content": "Sample the Busan specialty of dong-nae pajeon, a seafood and green onion pancake that is affordable and widely available.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Avoid Summer Peak Season",
            "content": "Visit outside July-August when rates are high and beaches are crowded. Spring and fall offer pleasant weather and lower prices.",
            "is_essential": False,
        },
    ],
    "Jeju": [
        {
            "category": "transport",
            "title": "Navigate by Bus with Google Maps",
            "content": "Jeju's bus system is efficient but only in Korean. Use Google Maps for accurate navigation across the island's routes.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Taste Local Hallabong Fruit",
            "content": "Try Jeju's famous hallabong, a sweet honeyed orange cultivated since the 1990s and a registered geographical specialty.",
            "is_essential": False,
        },
        {
            "category": "culture",
            "title": "Traditional Fishing and Diving Villages",
            "content": "Jeju's farm villages traditionally centered on farming alongside fishing and diving fishery in coastal fishing villages.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Visit Spring or Fall for Weather",
            "content": "Jeju winters are quite warm - Chinese cabbages are even left growing in the fields through the season.",
            "is_essential": False,
        },
    ],
    "Taipei": [
        {
            "category": "transport",
            "title": "Use EasyCard for Transit Discounts",
            "content": "Purchase an EasyCard for automatic discounts on metro and buses. Transfers between modes within an hour get discounted fares.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Taipei is Extremely Safe",
            "content": "Violent crime is rare. Stay alert in crowded areas for pickpockets and avoid isolated areas late at night.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Explore Night Markets for Street Food",
            "content": "Visit famous night markets like Shilin or Raohe for authentic Taiwanese street snacks, oyster omelets, and stinky tofu.",
            "is_essential": False,
        },
        {
            "category": "connectivity",
            "title": "Learn Basic Mandarin or Use Translation Apps",
            "content": "Most taxi drivers speak minimal English. Have destinations written in Chinese or use translation apps for easier navigation.",
            "is_essential": False,
        },
    ],
    "Sydney": [
        {
            "category": "transport",
            "title": "Use the Opal Card System",
            "content": "Purchase an Opal card at news agents or airport stations for discounted fares on trains, metro, light rail, ferries and buses.",
            "is_essential": True,
        },
        {
            "category": "money",
            "title": "Accommodation for Every Budget",
            "content": "Sydney offers hundreds of accommodation options, from backpacker hostels to five-star hotels with harbour and Opera House views.",
            "is_essential": False,
        },
        {
            "category": "food",
            "title": "Explore Multicultural Dining",
            "content": "Sydney's diverse cuisine reflects its multicultural community with affordable ethnic restaurants.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Beach Safety Between Flags",
            "content": "When swimming at beaches, always swim between the yellow and red flags.",
            "is_essential": True,
        },
    ],
    "Melbourne": [
        {
            "category": "transport",
            "title": "Use Myki Card for Transit",
            "content": "Purchase a myki card at Melbourne Airport or major stations for discounted public transport fares.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Explore Multicultural Cuisines",
            "content": "Melbourne's food scene is diverse with world-class restaurants throughout the city.",
            "is_essential": False,
        },
        {
            "category": "best_time",
            "title": "Book Ahead for January-March Events",
            "content": "From January to March, events like the Australian Open and the Grand Prix book out hostels and push up prices - reserve early.",
            "is_essential": False,
        },
        {
            "category": "culture",
            "title": "Ride the Iconic Tram Network",
            "content": "Melbourne's trams are a tourist attraction in their own right, running the largest tram network in the world.",
            "is_essential": False,
        },
    ],
    "Dubai": [
        {
            "category": "transport",
            "title": "Buy a NOL Card for Metro",
            "content": "The NOL Silver Card is the right option for most visitors: it gives a discount on single fares and free transfers.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Visit During Winter Months",
            "content": "Public transport is a comfortable option during Dubai's winter months, as long as you avoid rush hour on the red metro line.",
            "is_essential": True,
        },
        {
            "category": "etiquette",
            "title": "Respect Islamic Culture",
            "content": "Dress sensibly and avoid wearing revealing outfits, in keeping with local Islamic culture.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Try Traditional Emirati Cuisine",
            "content": "Traditional Emirati food centres on rice and meat cooked with spices; mandi is a popular, generally affordable meal.",
            "is_essential": False,
        },
    ],
    "Istanbul": [
        {
            "category": "transport",
            "title": "Use the Istanbulkart Transit Card",
            "content": "Purchase an Istanbulkart at metro stations for discounted fares on all public transport.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Try Roasted Chestnuts in Winter",
            "content": "Roasted chestnuts from street carts are a favourite warm winter snack, though sold year-round.",
            "is_essential": False,
        },
        {
            "category": "safety",
            "title": "Beware Mosque 'Guide' Scams",
            "content": "Near the Blue Mosque, be wary of friendly strangers who offer to guide you through the mosque and its surrounds - it is usually a scam.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Avoid Nightclub Drink Scams",
            "content": "High-drink-price scams occur at so-called night-clubs in Aksaray, Beyazit and Taksim that charge inflated bills off a replica menu.",
            "is_essential": True,
        },
    ],
    "New York": [
        {
            "category": "transport",
            "title": "Use OMNY for transit payment",
            "content": "OMNY is the contactless payment system for the MTA subway and bus lines. You can tap a contactless credit card, debit card, or mobile payment app to pay fares.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "New York is a safe destination",
            "content": "New York has a lower crime rate per person than the national average. Police have a strong presence in major public transportation hubs and crowded areas.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Guard your belongings on transit",
            "content": "The most common crime against tourists is bag snatching. Always keep your handbag secure and watch over your other bags.",
            "is_essential": True,
        },
    ],
    "Los Angeles": [
        {
            "category": "transport",
            "title": "Metro Rail reaches major destinations",
            "content": "The Metro Rail subway and light rail system connects most prominent neighborhoods and sightseeing destinations including Downtown L.A., Hollywood, Universal Studios, Chinatown, Santa Monica, and Pasadena.",
            "is_essential": True,
        },
        {
            "category": "safety",
            "title": "Exercise caution walking at night",
            "content": "Tourist destinations like Hollywood, Beverly Hills, and Santa Monica are safe. However, walking at night in some areas should be done with caution, ideally in groups.",
            "is_essential": True,
        },
        {
            "category": "food",
            "title": "Authentic immigrant cuisine throughout the city",
            "content": "Los Angeles offers diverse and inexpensive food representing the culinary traditions of its many immigrant communities.",
            "is_essential": True,
        },
        {
            "category": "best_time",
            "title": "Many hotels available at various price points",
            "content": "Los Angeles accommodations range from luxury hotels to budget hostels and apartment-style options. Check parking arrangements before booking.",
            "is_essential": False,
        },
    ],
    # END gh-237 city-tips
}

COUNTRY_SUMMARIES: dict[str, str] = {
    "Vietnam": "Vietnam is rewarding and affordable, with superb food and friendly people. Carry cash, use Grab to avoid taxi overcharging, and stay alert to motorbike bag-snatching in the cities.",
    "Thailand": "Thailand is easy and welcoming for travellers, with brilliant street food and good transport. Use Grab or metered taxis, treat the monarchy and Buddhism with respect, and ignore strangers steering you to gem shops.",
    "Singapore": "Singapore is ultra-safe, clean and efficient — the MRT gets you almost anywhere and contactless payment works everywhere. Just respect the strict laws on littering, eating on transport and (especially) drugs.",
    "Japan": "Japan is safe, punctual and spotless, but still surprisingly cash-based and big on etiquette. Carry cash, get an IC card, keep quiet on trains, and don't tip.",
    "Malaysia": "Malaysia is diverse, easy and affordable, with brilliant hawker food and good transport links. Use Grab to get around, carry ringgit cash for stalls and markets, and dress modestly out of respect for local Muslim customs.",
    "Indonesia": "Indonesia spans thousands of islands, from Bali's temples to Jakarta's sprawl, and runs largely on cash. Use Gojek or Grab for rides, drink only bottled water, and respect temple dress codes and the daily offerings on the streets.",
    "Philippines": "The Philippines is friendly and English-speaking, with stunning islands reached by budget flights and ferries. Carry peso cash once you leave the cities, build slack into island-hopping for weather, and check advisories for parts of Mindanao.",
    "Cambodia": "Cambodia is warm, affordable and home to the magnificent Angkor temples. The US dollar is everyday currency (bring clean small notes), tuk-tuks and ride apps get you around, and you should stick to marked paths in rural areas due to landmine risk.",
    "Laos": "Laos is laid-back, mountainous and refreshingly unhurried, with the new fast train making travel between Vientiane, Vang Vieng and Luang Prabang easy. It is very cash-based, ATMs are limited, and you should never stray off marked paths because of unexploded ordnance.",
    "Myanmar": "Myanmar holds extraordinary temples and culture but is affected by ongoing conflict and instability — check travel advisories carefully before going. International cards rarely work, so bring enough pristine US dollars for your whole trip and expect internet restrictions.",
    "Brunei": "Brunei is small, wealthy, very safe and quietly conservative, with grand mosques and pristine rainforest. There is little public transport so hiring a car is easiest, alcohol sales are banned, and modest dress and conservative behaviour are expected.",
    "Timor-Leste": "Timor-Leste is one of Asia's least-visited countries, with empty beaches and superb diving but very basic infrastructure. It uses the US dollar with few reliable ATMs, roads outside Dili are rough, so travel self-sufficiently and with good insurance.",
    "Hong Kong": "Hong Kong is fast, safe and effortless to get around — an Octopus card covers the MTR, buses, trams and ferries. Cards are accepted almost everywhere, the food scene from dim sum to street stalls is superb, and autumn is the most pleasant time to visit.",
    "South Korea": "South Korea is ultra-modern, exceptionally safe and a joy to navigate, with a cheap, English-signed transit network and lightning-fast internet. Get a T-money card, use Naver or Kakao Maps instead of Google, and visit in spring or autumn for the best weather.",
    # BEGIN gh-237 country-summaries
    "China": "China combines ancient history and rapid modernization, from bustling cities like Shanghai and Shenzhen to breathtaking natural wonders like Guilin's karst landscapes. The climate varies drastically from tropical south to subarctic north, with intensely hot summers and bitterly cold winters in the north.",
    "Taiwan": "Taiwan is one of the world's densest islands, featuring steep mountains, lush forests, and scenic sites including Taipei's bustling center. Lowland areas have humid summers, mild winters, and October to December offers the ideal weather for visiting.",
    "France": "France is the world's most-visited country, famous for fine dining, rich culture, and diverse landscapes from the French Riviera to the Alps. Paris remains the enchanting center, though every region offers unique treasures from Loire Valley châteaux to Celtic Brittany.",
    "United Kingdom": "The UK is a constitutional monarchy comprising England, Scotland, Wales, and Northern Ireland, each with unique culture and heritage. Known for centuries of history, eccentric popular culture, five major sports, and one of the world's best music scenes.",
    "Portugal": "Portugal is a modern country with strong historical links, famous for beautiful beaches, long warm summers, rich gastronomy, and cultural heritage. It combines contemporary development with traditional culture, handicrafts, and music.",
    "Italy": "Italy, the cradle of the Renaissance, is famous for its delicious cuisine, designer brands and landscapes from the seas to the mountains. Expect hot, dry summers, regional dialects alongside standard Italian, and a proud local food culture.",
    "Australia": "Australia is a vast, sun-drenched continent with unrivaled natural attractions, a laid-back culture that values informality, and ultramodern cities. Expect long distances between destinations, plentiful free WiFi, and frequent domestic flights that operate like a shuttle service between major hubs. The climate varies dramatically—tropical in the north, temperate in the south—so timing and preparation are critical for remote travel.",
    "United Arab Emirates": "The UAE blends ultramodern desert cities with traditional culture, offering world-class shopping, safety, and ease of travel. Vast resources and short distances make getting around effortless, while cash and cards are both widely accepted. A conservative dress code is advised outside resort zones, and extreme summer heat dominates—the best window for visiting is late autumn through early spring.",
    "Turkey": "Turkey bridges Europe and Asia, offering ancient ruins, vibrant cities, and warm hospitality. Long-distance buses are affordable and frequent with complimentary refreshments, while mobile SIMs are easy to acquire for tourists. Winters in the interior and east can be brutally cold, but coastal regions are more temperate. Tipping 10% at restaurants is customary, and security checkpoints are standard in major public spaces.",
    "United States": "The United States spans continental diversity—from tropical beaches to arctic tundra, bustling metropolises to remote wilderness. Credit cards are widely accepted, but carrying small bills for tips is essential. Domestic flights are frequent and often cheaper than trains or long drives. Fall and spring bring the most comfortable weather, while summer humidity and winter snow vary by region. Tipping 15–20% at restaurants and for services is an ingrained cultural norm.",
    # END gh-237 country-summaries
}

# Reject keys absent from countries.py; both dicts must cover the same countries.
_VALID_COUNTRIES: set[str] = {c["name"] for c in _COUNTRIES}
_unknown = (set(COUNTRY_TIPS) | set(COUNTRY_SUMMARIES)) - _VALID_COUNTRIES
if _unknown:
    raise ValueError(
        f"tips.py references unknown countries: {sorted(_unknown)} "
        "— add them to app/data/countries.py"
    )
if set(COUNTRY_TIPS) != set(COUNTRY_SUMMARIES):
    raise ValueError(
        "tips.py: COUNTRY_TIPS and COUNTRY_SUMMARIES must cover the same countries"
    )

# Reject CITY_TIPS keys not present in cities.py.
_VALID_CITIES: set[str] = {c["name"] for c in _CITIES}
_unknown_cities = set(CITY_TIPS) - _VALID_CITIES
if _unknown_cities:
    raise ValueError(
        f"tips.py: CITY_TIPS references unknown cities: {sorted(_unknown_cities)} "
        "— add them to app/data/cities.py"
    )

# Reject any tip whose category is not a recognised TipCategory value.
_VALID_CATEGORIES: set[str] = {c.value for c in _TipCategory}
for _tips in COUNTRY_TIPS.values():
    for _tip in _tips:
        if _tip["category"] not in _VALID_CATEGORIES:
            raise ValueError(
                f"tips.py: unknown tip category {_tip['category']!r} in COUNTRY_TIPS "
                "— add it to app.enums.TipCategory"
            )
for _tips in CITY_TIPS.values():
    for _tip in _tips:
        if _tip["category"] not in _VALID_CATEGORIES:
            raise ValueError(
                f"tips.py: unknown tip category {_tip['category']!r} in CITY_TIPS "
                "— add it to app.enums.TipCategory"
            )
