# mesh2gis — Yayınlama ve Bakım Kılavuzu

GitHub'a koymaktan PyPI'da yayınlamaya, sonrasında sürüm çıkarmaya kadar.

- [Yayınlamadan önce](#yayınlamadan-önce)
- [1. Yerel kurulum](#1-yerel-kurulum)
- [2. GitHub](#2-github)
- [3. PyPI — ilk yayın](#3-pypi--ilk-yayın)
- [4. Sonraki sürümler](#4-sonraki-sürümler)
- [Sürüm numaralama](#sürüm-numaralama)
- [CI ne yapıyor](#ci-ne-yapıyor)
- [Bakım](#bakım)
- [Yol haritası](#yol-haritası)

---

## Yayınlamadan önce

Sırasıyla halledilmesi gereken üç şey var:

**1. İsim müsaitliğini tekrar kontrol et.**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/mesh2gis/json
```

`404` → müsait. `200` → alınmış, isim değiştirmen gerekiyor.

⚠️ İsim kontrolü bayatlar. Repo kurmadan hemen önce bir daha bak.

**2. `pyproject.toml`'daki placeholder'ları değiştir.**

```toml
[project.urls]
Homepage  = "https://github.com/OWNER/mesh2gis"      # OWNER → kullanıcı adın
Issues    = "https://github.com/OWNER/mesh2gis/issues"
Changelog = "https://github.com/OWNER/mesh2gis/blob/main/CHANGELOG.md"
```

`authors` alanındaki isim ve `LICENSE`'daki telif satırı da senin.

**3. İsim değiştireceksen** — `mesh2gis` şu yerlerde geçer: `pyproject.toml`
(`name`, `[project.scripts]`, `[tool.hatch.build.targets.wheel] packages`,
`[tool.mypy] files`), `src/mesh2gis/` klasör adı, modül içi importlar,
`README.md`, `CHANGELOG.md`, `docs/`, `.github/workflows/ci.yml`.

---

## 1. Yerel kurulum

```bash
cd mesh2gis
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Dördü de temiz geçmeli. `uv` yoksa:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[all]' pytest pytest-cov ruff mypy
```

Kendi verinle bir kez de uçtan uca dene:

```bash
uv run mesh2gis inspect ornek.obj --group-by usemtl
uv run mesh2gis convert ornek.obj /tmp/test.shp --up y --epsg 5254
```

---

## 2. GitHub

```bash
git init
git add .
git commit -m "İlk sürüm: mesh2gis 0.1.0"
git branch -M main
git remote add origin https://github.com/KULLANICI/mesh2gis.git
git push -u origin main
```

`.gitignore` hazır — build artefaktları, cache'ler ve test çıktısı olarak
oluşan `.shp` / `.gpkg` dosyaları dışlanıyor.

⚠️ `.gitignore` `*.shp` ve `*.gpkg` içerdiği için, ileride **test verisi olarak
küçük bir shapefile eklemek istersen** `git add -f` gerekir.

Push'tan sonra repo ayarlarında yapılacaklar:

- **Description**: README'nin ilk cümlesi.
- **Topics**: `gis`, `3d`, `multipatch`, `shapefile`, `geopackage`, `obj`,
  `dxf`, `cad`, `arcgis`, `qgis`, `urban-planning`.
- **Settings → Actions → General**: workflow'ların çalıştığından emin ol.
- İlk CI koşusunun yeşil geçtiğini gör. Geçmiyorsa aşağıdaki "CI ne yapıyor"
  bölümüne bak.

---

## 3. PyPI — ilk yayın

Depoda saklanan API token'ı **yok**. Trusted publishing kullanıyoruz: PyPI,
GitHub Actions'tan gelen imzalı kimliği doğrudan tanıyor.

### 3.1 Önce TestPyPI ile prova (önerilir)

```bash
uv build
uvx twine check dist/*
uvx twine upload --repository testpypi dist/*
```

Sonra temiz bir ortamda kurulup çalıştığını doğrula:

```bash
python -m venv /tmp/deneme && /tmp/deneme/bin/pip install \
    --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ mesh2gis
/tmp/deneme/bin/mesh2gis --version
```

### 3.2 Trusted publisher tanımla

PyPI'da hesabın yoksa aç, sonra:

`https://pypi.org/manage/account/publishing/` → **Add a new pending publisher**

| Alan | Değer |
|---|---|
| PyPI Project Name | `mesh2gis` |
| Owner | GitHub kullanıcı adın |
| Repository name | `mesh2gis` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

"Pending publisher" projeyi önceden oluşturmanı gerektirmez — ilk yayında proje
otomatik oluşur.

### 3.3 GitHub'da environment oluştur

Repo → Settings → Environments → **New environment** → adı `pypi`.

`release.yml` bu ortamı kullanıyor. İstersen buraya "required reviewers"
ekleyip yayını onaya bağlayabilirsin.

### 3.4 Release yayınla

```bash
git tag -a v0.1.0 -m "mesh2gis 0.1.0"
git push origin v0.1.0
```

GitHub'da Releases → Draft a new release → tag `v0.1.0` → notları
`CHANGELOG.md`'den yapıştır → **Publish release**.

`release.yml` tetiklenir, `uv build` çalışır, `twine check` geçerse PyPI'ya
yükler. Actions sekmesinden izle.

⚠️ **PyPI'da aynı sürüm numarası iki kez yüklenemez.** 0.1.0 bozuk çıkarsa
silip yeniden yükleyemezsin; 0.1.1 çıkarman gerekir. TestPyPI provası tam da bu
yüzden var.

---

## 4. Sonraki sürümler

Her sürümde sırasıyla:

1. `pyproject.toml` → `version = "0.2.0"`
2. `src/mesh2gis/__init__.py` → `__version__ = "0.2.0"`
3. `CHANGELOG.md` → `[Unreleased]` altındakileri yeni sürüm başlığına taşı,
   tarihi yaz
4. `uv run pytest && uv run ruff check . && uv run mypy`
5. Commit, tag, push, GitHub release

⚠️ **Sürüm numarası iki yerde tutuluyor** ve elle senkron tutman gerekiyor.
Unutmak kolay — `hatch-vcs` kullanıp tag'den türetmek ileride yapılacaklar
listesinde.

Bir kontrol satırı:

```bash
grep -n 'version' pyproject.toml | head -2; grep -n '__version__' src/mesh2gis/__init__.py
```

---

## Sürüm numaralama

[Semantic Versioning](https://semver.org/). 0.x döneminde API'yi kırma
özgürlüğün var ama şeffaf ol:

- **0.1.x** — hata düzeltmeleri, dokümantasyon
- **0.2.0** — yeni özellik veya API değişikliği
- **1.0.0** — API'yi stabil ilan ettiğinde

Kıran değişiklikleri `CHANGELOG.md`'de `### Changed` altında **BREAKING** diye
işaretle.

---

## CI ne yapıyor

`.github/workflows/ci.yml`, dört iş:

| İş | Ne yapar |
|---|---|
| `lint` | Ruff check + Ruff format + mypy strict |
| `test` | 3 işletim sistemi × 4 Python sürümü (3.10–3.13) matrisi, pytest + coverage |
| `minimal-install` | **Extra'sız kurulup çalıştığını doğrular.** Paketin ana vaadi bu; birinin yanlışlıkla üst seviyeye `import ezdxf` koymasını yakalar. |
| `build` | `uv build` + `twine check`, artefaktları yükler |

`minimal-install` işi ayrıca `read_dxf`'in `ezdxf` yokken düzgün bir
`ImportError` verdiğini — traceback değil, "pip install 'mesh2gis[dxf]'" diyen
bir mesaj — test eder.

Coverage yüklemesi `CODECOV_TOKEN` secret'ı ister. Codecov kullanmayacaksan
`ci.yml`'den "Upload coverage" adımını sil.

---

## Bakım

**Gerçekçi ol.** Yayınlarsan issue gelir. Ayda 1–2 saat ayıramayacaksan
README'ye şöyle bir satır koy:

> Bu paket bir yan projedir. Issue'lara bakıyorum ama yanıt süresi garanti
> değil. PR'lar memnuniyetle karşılanır.

Bu tamamen meşru ve beklentiyi baştan doğru kurar.

**Alternatif:** PyPI'ya hiç çıkmadan GitHub'da bırakmak. `pip install
git+https://github.com/KULLANICI/mesh2gis` sorunsuz çalışır. Kullanıcı kitlen
dar ve tanıdıksa bu yeterli.

**Eklemeye değecek dosyalar** (şu an yok):

- `CONTRIBUTING.md` — kurulum, test çalıştırma, PR beklentileri
- `.github/ISSUE_TEMPLATE/bug_report.md` — girdi formatı, ihracatçı programı ve
  `inspect` çıktısını istemek yarı yarıya zaman kazandırır
- `CITATION.cff` — akademik kullanım olacaksa

**Gelen hata raporunda ilk isteyeceğin şey:** `mesh2gis inspect <dosya>`
çıktısı. Sorunların çoğu yanlış `--group-by` veya yanlış `--up`, ikisi de bu
çıktıda görünür.

---

## Yol haritası

Bilinçli olarak v0.1.0 dışında bırakılanlar:

**Kısa vade**
- `hatch-vcs` ile tek kaynaklı sürüm numarası
- STL ve PLY okuyucu (küçük iş, `trimesh` gerekmez)
- `--group-by` için otomatik seçim (`inspect` zaten hangisinin dolu olduğunu biliyor)
- `CONTRIBUTING.md` ve issue şablonu

**Orta vade**
- Yüz sarımını tutarlı hale getirme (şu an sadece koruyor, düzeltmiyor)
- Döndürme desteği (`--rotate`), 2 kontrol noktasından otomatik afin dönüşüm
- Büyük dosyalar için akış (streaming) modu
- Bina bazında birleştirmede taban geometrisi kesişimi — bbox yerine gerçek
  poligon; `merge_stacked`'ın yanlış birleştirmelerini büyük ölçüde çözer

**Uzun vade / belki hiç**
- glTF ve 3D Tiles çıktısı
- Texture taşıma (ArcGIS 3D object feature class hedefiyle)
- CityGML çıktısı

**Kapsam dışı:** fotogrametri mesh'leri (milyonlarca vertex, kaplamalı) —
ArcGIS'in kendi araçları bu işi zaten yapıyor ve bu paket onunla yarışmaya
çalışmamalı.
