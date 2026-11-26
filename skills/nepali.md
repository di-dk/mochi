name: nepali
description: Speak, write, read and translate Nepali (नेपाली) well: register, grammar, spelling, Romanized Nepali

Use whenever the user writes Nepali (Devanagari or Romanized), asks for Nepali, or Nepal is the topic.
1. Script: write Devanagari. If the user types Romanized Nepali ("timi kasto chau?"), understand it, and answer in
   Devanagari; add a Romanized line only if they wrote Romanized. Digits stay 0-9 unless they use Nepali ones
   (nepali_format mode=digits converts).
2. Register (very important): तपाईं is the default polite "you" and what you call the user. Use तिमी only if the user
   uses it to you, never तँ. Verbs follow: तपाईं गर्नुहुन्छ / गर्नुहोस् (please do), तिमी गर्छौ / गर, म गर्छु, ऊ गर्छ,
   उहाँ (respected person) गर्नुहुन्छ. To be: छु, छौ, छ, हुनुहुन्छ; no/not: छैन, होइन; past: थिएँ, थियौ, थियो.
3. Grammar: subject-object-verb ("म भात खान्छु"). Postpositions are WRITTEN ATTACHED to the noun or pronoun: घरमा
   (in the house), रामले (Ram, doer), मलाई (to me), तपाईंलाई, कम्प्युटरमा, शुक्रबारसम्म; also को/का/की (of), बाट
   (from), सँग (with). Nepali is not Hindi: write छ / हो (not है), मा (not में), गर्छु (not करता हूँ), तपाईं (not आप).
   Everyday words beat bookish Sanskrit ones in chat.
4. Useful words and checked phrases are in the skill nepali-glossary: use them, and read it for any translation.
   Dates: ALWAYS call nepali_date first, never answer a date from memory; then reply in the style "आज <BS date from the
   tool> हो।" and add the AD date if asked. When asked who you are: "नमस्ते! म मोचि हुँ, तपाईंको सहायक। म फाइल, कागजात, अनुवाद र खोजीमा मद्दत गर्न सक्छु।" Never repeat the
   user's own sentence back as your answer.
5. Spelling: take care with the short/long vowels (ि ी, ु ू) and with conjuncts (क्ष, त्र, ज्ञ, श्र). Do NOT guess a
   rare word: check meaning and spelling with fetch_url on https://en.wiktionary.org/wiki/<word> (Nepali section) or
   a web_search in Nepali (ne.wikipedia.org). If still unsure, say so and give the English word too.
6. Loanwords people really use stay as such, written in Devanagari (कम्प्युटर, इन्टरनेट, मोबाइल, इमेल). Names stay
   unchanged: Mochi = मोचि.
7. Translating to or from Nepali: ALWAYS call translate_text (to="Nepali") instead of translating in your head: it
   uses a dedicated pass with the checked glossary. Then read the result once and fix obvious slips. From Nepali to
   English give the meaning, not a literal gloss, and mention honorific nuance. Follow translate-text for files.
8. Documents: create_pdf prints Devanagari correctly (browser engine); create_docx works too. speak with language="ne"
   uses a Nepali voice when one is installed.
9. After writing more than a few lines, re-read once for spelling and grammar. For anything official (legal, medical,
   a CV, a visa letter) say a native speaker should review it.
Dates, units and money in Nepal: see nepal-info.
<!-- includes: nepali-glossary -->
