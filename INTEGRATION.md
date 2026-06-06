# Integrationsguide – Verifiering av Certificate of Origin

Detta dokument beskriver exakt hur appen ska anropa modellen för att verifiera ett
Certificate of Origin (certifikat) mot en faktura. Följ specen ordagrant — annars
avviker resultaten från det vi testat och validerat.

> **Appen ska köras SYNKRONT (ett ärende i taget) — INTE i batch-läge.**
> Batch-API:t används enbart internt för att köra hela testsetet billigt på en gång.
> En app som verifierar ett ärende åt gången ska anropa `POST /v1/chat/completions`
> direkt och få svaret omedelbart (se kodexemplet nedan).

---

## Översikt – två delar skickas till modellen

Varje verifiering är **ett** anrop till Chat Completions med två delar:

1. **System-prompt** – hela [`api_prompt.md`](api_prompt.md) ordagrant. Här ligger all
   beslutslogik. Den ändras inte mellan ärenden.
2. **User-meddelande** – ett tunt *dataomslag* (ingen instruktionstext) som bär:
   - faktura-PDF:en/erna som filbilagor, och
   - certifikatet som JSON i ett textblock med en **fast rubrikrad**.

Dessutom skickas **output-schemat** ([`schema_slim_strict.json`](schema_slim_strict.json))
som `response_format` så att svaret garanterat är giltig, strukturerad JSON.

---

## User-meddelandets struktur

`content` är en array. **Faktura-block först, JSON-textblock sist:**

```jsonc
"messages": [
  { "role": "system", "content": "<HELA api_prompt.md>" },
  { "role": "user", "content": [
      { "type": "file", "file": { "file_id": "file-abc..." } },   // en per faktura-PDF (1–3 st)
      { "type": "text",
        "text": "CERTIFICATE OF ORIGIN (structured JSON):\n{ ...hela certifikat-JSON... }" }
  ]}
]
```

**Måste-regler:**

- Textblocket **måste** börja med exakt raden `CERTIFICATE OF ORIGIN (structured JSON):\n`
  följt av certifikat-JSON:en. System-promptens §16 letar efter den rubriken.
- Faktura-`file`-block läggs **först**, JSON-`text`-blocket **sist**.
- Certifikat-JSON:en ska ha fältstrukturen enligt §16 i system-prompten
  (`Company`, `DeliveryCompany`, `OriginRows[]`, `CountryOfOrigin1/2/3`, …).
- **Varje `OriginRows[]`-post ska innehålla ett `Combined`-fält** = radens `Description`
  och `Quantity` sammanslagna till en sträng (t.ex. `"Net weight 2640 kg"`). Det krävs för
  att viktkategori (Gross/Net) på samma rad som viktvärdet ska godkännas (regel 4.4.2.1).
  Exempel: `{ "Description": "Net weight", "Quantity": "2640 kg", "Combined": "Net weight 2640 kg" }`.
- Faktura-PDF:erna laddas upp via **Files API** (`purpose: "user_data"`) för att få
  `file_id` — det är de id:na som refereras i `file`-blocken.

---

## Obligatoriska API-parametrar

| Parameter | Värde |
|---|---|
| `model` | `gpt-5.4` |
| `reasoning_effort` | `medium` |
| `response_format` | `json_schema`, `strict: true`, `name: "verification_output"`, schema = `schema_slim_strict.json` |
| `max_completion_tokens` | `16000` |

---

## Tolka svaret

Svaret ligger i `choices[0].message.content` som en **JSON-sträng** — parsa den.
Relevanta fält i `overall_assessment`:

- `comparison_result`: `IDENTICAL` | `NOT_IDENTICAL` | `MANUAL_REVIEW`
- `workflow_recommendation`: `AUTO_APPROVAL_ELIGIBLE` | `MANUAL_HANDLING_REQUIRED`
- `manual_review_reason`: strukturerat skäl när `comparison_result = MANUAL_REVIEW`, annars `NOT_APPLICABLE`. Värden: `SCANNED_UNREADABLE` (bildbaserad/oläsbar faktura), `AMBIGUOUS_MULTIPLE_INVOICES` (flera fakturor, oklart vilken), `ORIGIN_SUFFIX_UNEXPLAINED`, `IDENTIFIER_NOT_VERIFIABLE`, `OTHER`. Använd för att **routa** manuella ärenden (t.ex. `SCANNED_UNREADABLE` → begär bättre scan).
- `human_explanation`: kort förklaring på svenska för en handläggare

Auto-godkännande får ske endast när `workflow_recommendation = AUTO_APPROVAL_ELIGIBLE`
(vilket kräver `comparison_result = IDENTICAL`). I alla andra fall — inklusive
`MANUAL_REVIEW` — ska ärendet till manuell handläggning.

---

## C#-exempel (.NET 6+, synkront anrop)

Endast `HttpClient` + `System.Text.Json` — inget SDK-beroende, så `reasoning_effort`
och `file`-block fungerar garanterat.

```csharp
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

class CooVerifier
{
    private static readonly HttpClient Http = new();
    private const string ApiKey = "<OPENAI_API_KEY>";   // läs från config/secret, inte hårdkoda

    static async Task Main()
    {
        Http.DefaultRequestHeaders.Authorization =
            new AuthenticationHeaderValue("Bearer", ApiKey);

        // De två "prompterna" + schemat (ligger som filer hos er)
        string systemPrompt = await File.ReadAllTextAsync("api_prompt.md");
        JsonNode schema     = JsonNode.Parse(await File.ReadAllTextAsync("schema_slim_strict.json"))!;

        // Indata för ETT ärende: 1–3 faktura-PDF:er + certifikatet som JSON-sträng
        string[] invoicePdfPaths = { "invoice.pdf" };          // ev. flera
        string certJson = await File.ReadAllTextAsync("certificate.json");

        // 1) Ladda upp faktura-PDF:erna -> file_id
        var fileIds = new List<string>();
        foreach (var path in invoicePdfPaths)
            fileIds.Add(await UploadPdfAsync(path));

        // 2) Bygg user-meddelandet: faktura-block FÖRST, JSON-textblock SIST
        var userContent = new JsonArray();
        foreach (var id in fileIds)
            userContent.Add(new JsonObject
            {
                ["type"] = "file",
                ["file"] = new JsonObject { ["file_id"] = id }
            });
        userContent.Add(new JsonObject
        {
            ["type"] = "text",
            // OBS: rubrikraden MÅSTE vara exakt denna – system-prompten förväntar sig den
            ["text"] = "CERTIFICATE OF ORIGIN (structured JSON):\n" + certJson
        });

        // 3) Bygg request-body med de inställningar testerna kördes med (SYNKRONT, ej batch)
        var body = new JsonObject
        {
            ["model"]            = "gpt-5.4",
            ["reasoning_effort"] = "medium",
            ["max_completion_tokens"] = 16000,
            ["messages"] = new JsonArray
            {
                new JsonObject { ["role"] = "system", ["content"] = systemPrompt },
                new JsonObject { ["role"] = "user",   ["content"] = userContent }
            },
            ["response_format"] = new JsonObject
            {
                ["type"] = "json_schema",
                ["json_schema"] = new JsonObject
                {
                    ["name"]   = "verification_output",
                    ["strict"] = true,
                    ["schema"] = schema
                }
            }
        };

        // 4) Anropa Chat Completions (direkt svar)
        var resp = await Http.PostAsync(
            "https://api.openai.com/v1/chat/completions",
            new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json"));
        resp.EnsureSuccessStatusCode();

        var doc = JsonNode.Parse(await resp.Content.ReadAsStringAsync())!;
        string resultJson = doc["choices"]![0]!["message"]!["content"]!.GetValue<string>();

        // resultJson = verifierings-JSON som validerar mot schemat
        // overall_assessment.comparison_result = IDENTICAL | NOT_IDENTICAL | MANUAL_REVIEW
        Console.WriteLine(resultJson);
    }

    // Files API: ladda upp PDF med purpose "user_data", returnera file_id
    static async Task<string> UploadPdfAsync(string path)
    {
        using var form = new MultipartFormDataContent();
        form.Add(new StringContent("user_data"), "purpose");
        var bytes = new ByteArrayContent(await File.ReadAllBytesAsync(path));
        bytes.Headers.ContentType = new MediaTypeHeaderValue("application/pdf");
        form.Add(bytes, "file", Path.GetFileName(path));

        var resp = await Http.PostAsync("https://api.openai.com/v1/files", form);
        resp.EnsureSuccessStatusCode();
        var doc = JsonNode.Parse(await resp.Content.ReadAsStringAsync())!;
        return doc["id"]!.GetValue<string>();
    }
}
```

---

## Checklista före driftsättning

- [ ] System-prompten skickas ordagrant från `api_prompt.md`.
- [ ] Textblocket inleds med exakt `CERTIFICATE OF ORIGIN (structured JSON):\n`.
- [ ] Faktura-PDF:er uppladdade med `purpose: "user_data"`, refererade som `file`-block (först).
- [ ] `model=gpt-5.4`, `reasoning_effort=medium`, `max_completion_tokens=16000`.
- [ ] `response_format` = `json_schema` (strict) med `schema_slim_strict.json`.
- [ ] Synkront anrop (`/v1/chat/completions`) — **inte** batch.
- [ ] Svaret parsas ur `choices[0].message.content`; routing styrs av `workflow_recommendation`.
