// Loads the map data from Firestore. Records are stored as a few JSON-string chunks per layer
// (see scripts/upload_firestore.py), so one page view costs about ten document reads.
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.0.2/firebase-app.js";
import { getFirestore, doc, getDoc, collection, getDocs, query, where } from "https://www.gstatic.com/firebasejs/11.0.2/firebase-firestore-lite.js";
import { firebaseConfig } from "./config.js";

const db = getFirestore(initializeApp(firebaseConfig));

async function loadLayer(layer, expected) {
  const snap = await getDocs(query(collection(db, "map_chunks"), where("layer", "==", layer)));
  const chunks = snap.docs.map((d) => d.data()).sort((a, b) => a.i - b.i);
  if (chunks.length !== expected) throw new Error(`${layer}: expected ${expected} chunks, found ${chunks.length}`);
  return chunks.flatMap((c) => JSON.parse(c.json));
}

export async function loadAll() {
  const metaSnap = await getDoc(doc(db, "map", "meta"));
  if (!metaSnap.exists()) throw new Error("The map data has not been uploaded yet.");
  const meta = metaSnap.data();
  const [places, venues, hexes, groups] = await Promise.all(["places", "venues", "hexes", "groups"].map((l) => loadLayer(l, meta.chunks[l])));
  return { meta, places, venues, hexes, groups: new Map(groups.map((g) => [g.id, g])) };
}
