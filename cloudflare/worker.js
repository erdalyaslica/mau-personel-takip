const REPO = "erdalyaslica/mau-personel-takip";
const STATE = "rehber_durumu.csv";

async function telegram(env, text) {
  const response = await fetch(`https://api.telegram.org/bot${env.TG_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: env.TG_ALLOWED_CHAT_ID, text }),
  });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(`Telegram sendMessage: ${response.status}`);
}

async function github(env, path, init = {}) {
  const response = await fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...init,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GH_TOKEN}`,
      "User-Agent": "maltepe-personel-telegram-webhook",
      ...(init.headers || {}),
    },
  });
  if (!response.ok) throw new Error(`GitHub API: ${response.status}`);
  return response.status === 204 ? null : response.json();
}

function csvRow(line) {
  const fields = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') {
      if (quoted && line[i + 1] === '"') { field += '"'; i++; }
      else quoted = !quoted;
    } else if (c === "," && !quoted) { fields.push(field); field = ""; }
    else field += c;
  }
  fields.push(field);
  if (fields.length < 7 || fields[0].replace(/^\uFEFF/, "") === "Unvan") return null;
  return { name: `${fields[1]} ${fields[2]}`.trim(), unit: fields[3], email: fields[5] };
}

function personKey(person) {
  return (person.email || person.name).trim().toLocaleLowerCase("tr");
}

async function recent(env) {
  const commits = await github(env, `/commits?path=${STATE}&sha=main&per_page=35`);
  const events = [];
  for (const item of commits) {
    const commit = await github(env, `/commits/${item.sha}`);
    const patch = commit.files?.find(file => file.filename === STATE)?.patch;
    if (!patch) continue;
    const old = new Map(), current = new Map();
    for (const line of patch.split("\n")) {
      if (!/^[+-]/.test(line) || /^(---|\+\+\+)/.test(line)) continue;
      const person = csvRow(line.slice(1));
      if (person) (line[0] === "+" ? current : old).set(personKey(person), person);
    }
    const date = new Intl.DateTimeFormat("tr-TR", {
      timeZone: "Europe/Istanbul", day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).format(new Date(item.commit.committer.date));
    for (const key of new Set([...old.keys(), ...current.keys()])) {
      const previous = old.get(key), next = current.get(key);
      if (previous && next && previous.name === next.name && previous.unit === next.unit) continue;
      const kind = previous && next ? "🟡 Güncellendi" : next ? "🟢 Yeni" : "🔴 Ayrıldı";
      events.push(`${kind} · ${date}\n• ${(next || previous).name}\n  └ ${(next || previous).unit}`);
      if (events.length === 5) break;
    }
    if (events.length === 5) break;
  }
  return events.length ? `🕘 Son ${events.length} personel değişikliği\n\n${events.join("\n\n")}`
    : "ℹ️ Son personel değişiklikleri Git geçmişinden bulunamadı.";
}

function command(text) {
  const normalized = (text || "").trim().toLocaleLowerCase("tr").replace(/\s+/g, " ").replace(/^\/([^ @]+)@[^ ]+/, "/$1");
  if (["/kontrol", "kontrol"].includes(normalized)) return "control";
  if (["/son5", "/son 5", "son5", "son 5"].includes(normalized)) return "recent";
  if (["/start", "/help", "/yardım", "/yardim", "yardım", "yardim"].includes(normalized)) return "help";
  return normalized ? "unknown" : "ignore";
}

async function handle(update, env) {
  const message = update.message;
  if (!message || String(message.chat?.id) !== env.TG_ALLOWED_CHAT_ID) return;
  const action = command(message.text);
  if (action === "ignore") return;
  if (action === "help" || action === "unknown") {
    await telegram(env, `${action === "unknown" ? "❓ Komutu anlayamadım.\n\n" : ""}📚 Personel Rehber Botu\n/kontrol — rehberi tarar ve sonucu bildirir\n/son5 — son 5 değişikliği gösterir\n/yardım — komutları gösterir`);
  } else if (action === "recent") {
    await telegram(env, await recent(env));
  } else if (action === "control") {
    await github(env, "/actions/workflows/personel-rehber-kontrol.yml/dispatches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main", inputs: { webhook_control: "true" } }),
    });
    await telegram(env, "⏳ Rehber kontrolü GitHub'da başlatıldı. Tarama bitince sonuç burada bildirilecek.");
  }
}

export default {
  async fetch(request, env, ctx) {
    if (new URL(request.url).pathname !== "/telegram" || request.method !== "POST") {
      return new Response("Not found", { status: 404 });
    }
    if (!env.WEBHOOK_SECRET || request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }
    const update = await request.json();
    try {
      await handle(update, env);
    } catch (error) {
      console.error("Telegram command failed", String(error));
      if (String(update.message?.chat?.id) === env.TG_ALLOWED_CHAT_ID) {
        try { await telegram(env, "⚠️ Komut tamamlanamadı. Bot yöneticisi GitHub/Worker kayıtlarını kontrol etmeli."); }
        catch (sendError) { console.error("Failure message could not be delivered", String(sendError)); }
      }
    }
    return new Response("OK");
  },
};
