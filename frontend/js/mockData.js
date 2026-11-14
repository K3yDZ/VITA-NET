// mockData.js — placeholder crew + simulated sensor stream + roster management

const HISTORY_LEN = 60;

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function step(prev, driftMax, lo, hi) { return clamp(prev + (Math.random() * 2 - 1) * driftMax, lo, hi); }

const DEFAULT_CREW = [
  { id: "a1", name: "Mara Ibáñez", role: "Commander", dossier: { baseline:{hr:68,bpSys:118,bpDia:76}, allergies:["Penicillin"], meds:["Multivitamin","Omega-3"], sleepH:6.8 } },
  { id: "a2", name: "Kenji Watanabe", role: "Flight Engineer", dossier: { baseline:{hr:62,bpSys:112,bpDia:72}, allergies:["None"], meds:["Vitamin D"], sleepH:7.2 } },
  { id: "a3", name: "Amara Bello", role: "Mission Specialist", dossier: { baseline:{hr:70,bpSys:120,bpDia:78}, allergies:["Peanuts"], meds:["Antihistamine"], sleepH:6.5 } },
  { id: "a4", name: "Deniz Aydın", role: "Medical Officer", dossier: { baseline:{hr:65,bpSys:115,bpDia:74}, allergies:["None"], meds:["None"], sleepH:7.8 } },
  { id: "a5", name: "Priya Sharma", role: "Mission Specialist", dossier: { baseline:{hr:66,bpSys:116,bpDia:75}, allergies:["None"], meds:["Iron"], sleepH:7.0 } },
  { id: "a6", name: "Carlos Mendes", role: "Mission Specialist", dossier: { baseline:{hr:64,bpSys:114,bpDia:73}, allergies:["Sulfa"], meds:["None"], sleepH:7.5 } },
];

const ROLES = ["Mission Specialist", "Flight Engineer", "Medical Officer", "Payload Specialist", "Systems Engineer", "Science Officer", "Communications Officer", "Navigation Officer"];
const FIRST_NAMES = ["Alex", "Jordan", "Taylor", "Casey", "Morgan", "Riley", "Avery", "Quinn", "River", "Sage", "Dakota", "Phoenix", "Rowan", "Skyler", "Emerson", "Finley", "Hayden", "Kendall", "Logan", "Marley"];
const LAST_NAMES = ["Chen", "Rodriguez", "Patel", "Kim", "Singh", "Williams", "Brown", "Garcia", "Martinez", "Anderson", "Thompson", "White", "Harris", "Clark", "Lewis", "Robinson", "Walker", "Young", "King", "Scott"];

function generateAdditionalCrew(startId, count) {
  const crew = [];
  for (let i = 0; i < count; i++) {
    const id = startId + i;
    const firstName = FIRST_NAMES[Math.floor(Math.random() * FIRST_NAMES.length)];
    const lastName = LAST_NAMES[Math.floor(Math.random() * LAST_NAMES.length)];
    const name = `${firstName} ${lastName}`;
    const role = ROLES[Math.floor(Math.random() * ROLES.length)];
    crew.push({
      id: `a${id}`,
      name,
      role,
      dossier: {
        baseline: { hr: 60 + Math.random() * 20, bpSys: 110 + Math.random() * 20, bpDia: 70 + Math.random() * 10 },
        allergies: ["None"],
        meds: ["None"],
        sleepH: 6.5 + Math.random() * 1.5,
      },
    });
  }
  return crew;
}

export function createRoster(count = 6) {
  const crewCount = Math.max(1, Math.min(count, 200));
  const now = Date.now();

  // Use DEFAULT_CREW for first 6, then generate additional
  let crewList = [...DEFAULT_CREW];
  if (crewCount > DEFAULT_CREW.length) {
    crewList = crewList.concat(generateAdditionalCrew(7, crewCount - DEFAULT_CREW.length));
  }

  return crewList.slice(0, crewCount).map((c) => ({
    ...c,
    initials: c.name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase(), dossier: c.dossier,
    mode: "live",
    radiationMSv: Math.random() * 8,
    vitals: seedVitals(),
    history: [],
    missionStart: now,
  }));
}

function seedVitals() {
  return {
    heartRate: 62 + Math.random() * 14,
    bpSys: 108 + Math.random() * 14,
    bpDia: 68 + Math.random() * 10,
    spo2: 97 + Math.random() * 2,
    tempC: 36.5 + Math.random() * 0.4,
    stressIndex: 15 + Math.random() * 20,
    hrv: 45 + Math.random() * 20,
  };
}

export function addAstronaut(roster, { name, role }) {
  const id = "a" + Date.now().toString(36) + Math.random().toString(36).slice(2, 4);
  const now = Date.now();
  roster.push({
    id, name: name.trim(), role: role.trim() || "Crew Member",
    initials: name.trim().split(/\s+/).map(p => p[0]).join("").slice(0, 2).toUpperCase(), dossier: { baseline:{hr:68,bpSys:118,bpDia:76}, allergies:["None"], meds:["None"], sleepH:7.0 },
    mode: "live",
    radiationMSv: Math.random() * 8,
    vitals: seedVitals(),
    history: [],
    missionStart: now,
  });
  return roster[roster.length - 1];
}

export function removeAstronaut(roster, id) {
  const idx = roster.findIndex(a => a.id === id);
  if (idx !== -1) roster.splice(idx, 1);
}

export function tickVitals(astronaut) {
  if (astronaut.mode === "manual") return astronaut.vitals;
  const v = astronaut.vitals;
  const next = {
    heartRate: step(v.heartRate, 3, 45, 150),
    bpSys: step(v.bpSys, 2.5, 85, 175),
    bpDia: step(v.bpDia, 2, 55, 115),
    spo2: clamp(step(v.spo2, 0.6, 88, 100), 88, 100),
    tempC: step(v.tempC, 0.05, 35.2, 39.2),
    stressIndex: clamp(step(v.stressIndex, 4, 0, 100), 0, 100),
    hrv: clamp(step(v.hrv, 3, 15, 90), 15, 90),
  };
  const baseRate = 0.02 + Math.random() * 0.03;
  const eventBump = Math.random() < 0.01 ? Math.random() * 4 : 0;
  astronaut.radiationMSv = astronaut.radiationMSv + baseRate + eventBump;
  astronaut.vitals = next;
  pushHistory(astronaut);
  return next;
}

function pushHistory(astronaut) {
  astronaut.history.push({ t: Date.now(), ...astronaut.vitals, radiationMSv: astronaut.radiationMSv });
  if (astronaut.history.length > HISTORY_LEN) astronaut.history.shift();
}

export function applyManualVitals(astronaut, patch) {
  astronaut.mode = "manual";
  const vitalsPatch = {};
  const directKeys = ["heartRate","bpSys","bpDia","spo2","tempC","stressIndex","hrv"];
  for (const k of directKeys) if (patch[k] !== undefined && !isNaN(patch[k])) vitalsPatch[k] = patch[k];
  astronaut.vitals = { ...astronaut.vitals, ...vitalsPatch };
  if (patch.radiationMSv !== undefined && !isNaN(patch.radiationMSv)) astronaut.radiationMSv = patch.radiationMSv;
  pushHistory(astronaut);
}

export function setMode(astronaut, mode) { astronaut.mode = mode; }
