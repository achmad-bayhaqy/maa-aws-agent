---
name: maa-kb-authoring
description: "Muat skill ini saat pengguna minta menambah/memperbaiki isi Knowledge Base atau membuat skill baru."
---

# KB & Skills Authoring
Muat skill ini saat pengguna minta menambah/memperbaiki isi Knowledge Base atau membuat skill baru.

## Update KB via perintah
- List: kb_list_docs -> Baca: kb_read_doc(key) -> Edit: kb_write_doc(key, content) -> Hapus: kb_delete_doc(key) -> Re-index otomatis terpicu; bila perlu paksa kb_sync.
- Dokumen baru: kb_write_doc dengan key docs/<slug>.md (markdown, fokus, 200-2000 kata).
- Kualitas: judul jelas, strukturnya H2/H3, poin padat; tanpa duplikasi dokumen lain (baca dulu yang ada).

## Membuat skill baru (untuk agent)
- Skill = file skills/<nama-skill>.md berisi prosedur eksperti yang dapat dieksekusi agent.
- Struktur ideal: judul -> kapan dipakai -> prosedur bernomor -> aturan keras (WAJIB/JANGAN) -> contoh output.
- Simpan via kb_write_doc TIDAK bisa (harus prefix docs/) — jadikan dokumen docs/skill-<nama>.md dan sarankan superadmin memindahkannya via UI KB, atau tulis langsung dengan tool s3 put ke skills/ bila tersedia.
- Nama skill: lowercase-kebab, 2-5 kata, deskriptif (mis. "incident-response-aws").
