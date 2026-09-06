# mesh2gis — Kullanım Kılavuzu

CAD kütle modellerini (OBJ, DXF) GIS'e hazır 3B feature'lara çevirir. ArcGIS
lisansı, GDAL veya derlenmiş bağımlılık gerektirmez.

- [Kurulum](#kurulum)
- [Üç adımlık iş akışı](#üç-adımlık-iş-akışı)
- [`inspect` — önce buna bak](#inspect--önce-buna-bak)
- [`convert` — dönüştürme](#convert--dönüştürme)
- [Gruplama stratejileri](#gruplama-stratejileri)
- [Georeferans](#georeferans)
- [Çıktı formatları ve öznitelikler](#çıktı-formatları-ve-öznitelikler)
- [Python API](#python-api)
- [Tarifler](#tarifler)
- [Sorun giderme](#sorun-giderme)
- [Bilinen sınırlar](#bilinen-sınırlar)

---

## Kurulum

```bash
pip install mesh2gis                 # çekirdek: OBJ okuma, SHP/GPKG/OBJ yazma
pip install 'mesh2gis[dxf]'          # + DXF okuma (ezdxf)
pip install 'mesh2gis[crs]'          # + tüm EPSG kodları (pyproj)
pip install 'mesh2gis[all]'          # hepsi
```

Çekirdek bağımlılıklar sadece `numpy` ve `pyshp`. `[crs]` olmadan da EPSG
5253–5259 (TUREF 3 derecelik TM dilimleri) ve 4326 gömülü tablodan çözülür —
yani Türkiye işleri için pyproj kurmana gerek yok.

Python 3.10+.

---

## Üç adımlık iş akışı

Her dosya için sırayla:

**1. Bak.** Dosyanın neye benzediğini öğren. Hangi `--group-by` ve
`--storey-height` gerektiğini bu adım söyler.

```bash
mesh2gis inspect kutle.obj --group-by usemtl
```

**2. Çevir.**

```bash
mesh2gis convert kutle.obj kutle.shp \
    --up y --group-by usemtl --epsg 5254 --storey-height 3.2
```

**3. Doğrula.** Çıktıyı ArcGIS Pro'da bir **Local Scene**'e (Map değil) veya
QGIS'e at, halihazır katmanını üstüne aç, çakışıyor mu bak.

Bu sırayı atlama. `inspect` çalıştırmadan `convert` yaparsan yanlış eksende
veya tek feature olarak çıkan bir dosyayı sonradan fark edersin.

---

## `inspect` — önce buna bak

```bash
mesh2gis inspect <dosya> [--group-by STRATEJİ] [--up {y,z}]
```

Hiçbir şey yazmaz, sadece raporlar:

```
source     Master_Blok_OBJ.obj
vertices   401,436
faces      235,429
  arity    3-gon: 172,538, 4-gon: 62,891
bounds X   437,170.750 … 441,986.694   (span 4,815.944)
bounds Y   -0.250 … 28.800   (span 29.050)
bounds Z   -4,537,329.079 … -4,534,573.037   (span 2,756.042)
up axis    y (guess)
tags
  usemtl     8,604 distinct
  g          absent
  o          absent
group_by=usemtl: 8,604 features
  heights  3.2: 4,274, 9.6: 2,167, 12.8: 1,042, 16.0: 642, 19.2: 222 …   (up=y)
  hint     98% of heights are multiples of 3.2 -- try --storey-height 3.2
```

Bu çıktıdan okuman gerekenler:

| Satır | Ne söyler |
|---|---|
| `bounds` | Koordinatlar gerçek dünyada mı, lokal mi? Yukarıdaki örnekte X ~437.000 / Z ~4.535.000 → TM koordinatı, öteleme gerekmiyor. 0 civarı sayılar görürsen `--offset` lazım. |
| `up axis` | Hangi eksenin dikey olduğu tahmini. Yükseklik span'i (29 m) yatay span'lerin (4.816 m, 2.756 m) yanında çok küçükse doğru tahmin etmiştir. |
| `tags` | Hangi gruplama anahtarının mevcut olduğu. `usemtl 8.604 distinct`, `g absent`, `o absent` → Rhino çıktısı, `--group-by usemtl` şart. |
| `heights` | Yükseklik histogramı. |
| `hint` | Kat yüksekliği tahmini ve kaç yüzde tuttuğu. |

⚠️ `up axis` sonunda `(guess)` yazıyorsa tahmindir. Sezgi şu: kütle modelleri
yüksek değil, geniştir — en kısa eksen dikeydir. **Tek bir kuleyi veya tek
adayı** modellemişsen bu varsayım çöker, `--up` ile elle söyle.

---

## `convert` — dönüştürme

```bash
mesh2gis convert <girdi> <çıktı> [seçenekler]
```

Çıktı formatı uzantıdan seçilir: `.shp`, `.gpkg`, `.obj`.

| Seçenek | Varsayılan | Açıklama |
|---|---|---|
| `--up {y,z}` | otomatik | Girdinin dikey ekseni. Rhino ve SketchUp genelde `y`. |
| `--group-by` | `usemtl` | Feature'lara bölme stratejisi. Aşağıya bak. |
| `--offset X Y Z` | `0 0 0` | Dünya koordinatına öteleme. Ölçeklemeden **sonra** uygulanır. |
| `--scale N` | `1.0` | Birim dönüşümü (mm → m için `0.001`). |
| `--epsg N` | yok | Çıktının koordinat sistemi. Verilmezse `.prj` yazılmaz. |
| `--storey-height M` | yok | Kat yüksekliği; `STOREYS` ve `FLOOR_AREA` bundan türetilir. `auto` yazarsan veriden çıkarır. |
| `--merge-stacks` | kapalı | Üst üste binen blokları bina bazında birleştirir. |
| `-q`, `--quiet` | kapalı | İlerleme çıktısını sustur. |

İşlem sırası sabittir: **eksen çevirme → ölçekleme → öteleme → gruplama →
(varsa) yığın birleştirme → yazma.** Ölçek öteleme öncesinde uygulandığı için
`--scale 0.001` verdiğinde georeferans kayması da 1000'e bölünmez.

---

## Gruplama stratejileri

CAD dosyası aslında bir "poligon çorbası"dır. Hangi yüzün hangi binaya ait
olduğunu belirleyen tek şey ihracatçının yazdığı etiketlerdir ve her program
farklı yazar. **Yanlış strateji seçersen ya tek dev feature ya da binlerce
parça elde edersin.**

| `--group-by` | Ne zaman |
|---|---|
| `o` | İhracatçı gerçek obje adı yazmış. En temizi. |
| `g` | Grup adı yazmış. |
| `usemtl` | **Rhino OBJ.** Rhino hiç `g`/`o` yazmaz, her obje için `usemtl` satırını tekrarlar — malzeme tekrarı fiilî obje sınırı olur. |
| `layer` | **DXF.** Katman doğal anahtardır. |
| `connected` | Kullanılabilir etiket yok. Topolojik: ortak vertex'i olan yüzler aynı feature. Duvarı paylaşan bitişik nizam binaları birleştirir. |
| `single` | Tüm mesh tek feature olsun. |

`inspect` çıktısındaki `tags` bölümü hangisinin mevcut olduğunu söyler. Hepsi
`absent` ise `connected` kullan.

### `--merge-stacks`

Ayrı bir geçiştir, gruplamadan sonra çalışır. Kütle modellerinde bir bina
genelde **ana kütle + çekme kat** olarak iki ayrı blok çizilir. Bu bayrak,
tabanı çakışan **ve** üst/alt kotu birbirine denk gelen blokları tek feature'da
birleştirir.

İki koşul da gerekli: sadece kot bakılırsa düz arazideki komşular birleşir,
sadece taban bakılırsa sıra evler birleşir.

⚠️ **Sezgisel bir yöntemdir.** Hem duvarı paylaşan hem kat yüksekliği aynı olan
komşu binaları yanlışlıkla birleştirebilir. Bina bazında kat sayısına
güvenmeden önce sonucu gözle doğrula. Python API'sinde `tolerance` ve
`overlap_ratio` ile hassasiyeti ayarlayabilirsin.

Örnek: 8.604 blok → `--merge-stacks` → 4.116 bina.
Birleştirilmiş feature'lar **parça parça ölçülür**, birleşim üzerinden değil.
Bunun sebebi geometrik: üst üste oturan iki katının ara yüzeyindeki kenarlar iki
değil dört yüz tarafından paylaşılır, yani birleşim kapalı bir manifold değildir
ve hacmi integre edilemez. Parçalar ise kapalı katılardır; hacimleri toplanır.
`N_PARTS` alanı bir feature'ın kaç bloktan geldiğini söyler.


---

## Georeferans

OBJ ve DXF koordinat sistemi taşımaz. Üç senaryo var:

### 1. Koordinatlar zaten gerçek dünyada

`inspect` çıktısında X ~400.000, Y ~4.500.000 gibi değerler görüyorsan model
zaten TM koordinatındadır. Sadece `--epsg` ver:

```bash
mesh2gis convert kutle.obj kutle.shp --up y --epsg 5254
```

### 2. Model 0,0,0 merkezli

`--offset` ile ötele. Öteleme değerini bulmak için: modeldeki tanıdık bir
noktanın (bina köşesi, kavşak) hem CAD'deki hem halihazırdaki koordinatını oku,
farkı al.

```bash
mesh2gis convert kutle.obj kutle.shp \
    --up y --offset 436372.01 -4533303.26 0 --epsg 5254
```

⚠️ `--offset`'in Y bileşenini **eksen çevirmeden sonraki** sisteme göre ver.
Y-up bir dosyada `X=x, Y=-z, Z=y` dönüşümü uygulanır; öteleme bundan sonra
gelir. Emin değilsen küçük bir offset'le bir kez çevir, `inspect`'in `bounds`
satırından kontrol et.

### 3. Döndürme de gerekiyor

Paket döndürme yapmaz. Önce çevir, sonra ArcGIS Pro'da Scene'de
Modify Features → Move/Rotate ile oturt.

### Koordinat sistemi seçimi

Gömülü tablo: **4326** (WGS 84) ve **5253–5259** (TUREF / TM27, TM30, TM33,
TM36, TM39, TM42, TM45). Başka bir EPSG kodu için `[crs]` extra'sı gerekir.

⚠️ **Datum'u karıştırma.** `.prj` sadece etiket yazar, geometriyi taşımaz.
Model ED50'den geliyorken TUREF etiketi koyarsan halihazırla metrelerce kayar.
Kayma görürsen ArcGIS Pro'da Define Projection ile doğru datum'u seç — geometri
bozulmaz, sadece etiket değişir.

---

## Çıktı formatları ve öznitelikler

| Uzantı | Geometri | Not |
|---|---|---|
| `.shp` | MultiPatch (triangle fan) | ArcGIS'te gerçek 3B katı. `--epsg` verilirse `.prj` de yazılır. Yanında `.shx` ve `.dbf` oluşur — **dördü aynı klasörde ve aynı isimde kalmalı.** |
| `.gpkg` | MultiPolygonZ | QGIS, GDAL, PostGIS eklentisiz açar. Saf `sqlite3` ile yazılır. |
| `.obj` | Wavefront OBJ | CAD'e temiz geri dönüş; `g` grupları eklenir, curve/bspline artıkları atılır. |

Neden `.shp` için MultiPatch: ArcGIS'in gerçek 3B katı olarak gördüğü tek
shapefile geometrisi budur. Her yüz kendi `TRIANGLE_FAN` part'ı olur — üçgen ve
dörtgenler olduğu gibi geçer, n-gon'lar ilk vertex'ten yelpazelenir.

Neden `.gpkg` için MultiPolygonZ değil de PolyhedralSurfaceZ değil:
PolyhedralSurface kapalı katıyı daha doğru modeller ama GeoPackage'ın çekirdek
geometri kümesinde değil ve okuyucu desteği düzensiz. MultiPolygonZ her yerde
açılır.

### Öznitelik tablosu

Şema veriye göre değişir — sabit değil. **Bir sütun ancak anlamlı
hesaplanabiliyorsa yazılır.** Kütle modeli, köprü, makine parçası, arazi
yüzeyi… her biri kendi tablosunu alır.

**Her zaman yazılanlar** — bunlar herhangi bir katı için anlamlı:

| Shapefile | GeoPackage | İçerik |
|---|---|---|
| `BLOCK_ID` | `block_id` | 1'den başlayan sıra no |
| `LABEL` | `label` | Grubun geldiği etiket (malzeme adı, katman adı) |
| `Z_MIN` / `Z_MAX` | `z_min` / `z_max` | Oturma kotu / üst kot |
| `HEIGHT` | `height` | `Z_MAX - Z_MIN` |

| `BASE_AREA` | `base_area` | **Sadece zemine oturan** yatay yüzlerin alanı — TAKS için doğru olan bu, kat alanlarının toplamı değil |
| `SURF_AREA` | `surface_area` | Tüm yüzlerin toplam alanı. Hacimden farklı olarak **açık mesh'lerde de** anlamlı |
| `N_PARTS` | `n_parts` | Feature kaç bloktan birleşti (birleşmemişse 1) |
| `VOLUME` | `volume` | Kapalı hacim. **Kapalı olmayan blokta 0.** |
| `CLOSED` | `closed` | Her kenar tam iki yüz tarafından paylaşılıyor mu |
| `N_FACES` | `n_faces` | Yüz sayısı |

**Sadece `--storey-height` verilirse:**

| Shapefile | GeoPackage | İçerik |
|---|---|---|
| `STOREYS` | `storeys` | `HEIGHT / --storey-height`, yuvarlanmış |
| `FLOOR_AREA` | `floor_area` | Toplam inşaat alanı: her parçanın kendi tabanı × kendi kat sayısı |

`auto` yazarsan program kat gridini blok yüksekliklerinden kendi bulur ve
hangi değeri seçtiğini, kaç yüzde tuttuğunu yazar:

```
storey height inferred as 3.2 (95% of heights fit); this is a guess --
pass an explicit value to override
```

⚠️ `auto` bir ölçüm değil, öneri. Çözemediği bir belirsizlik var: 3,2'nin her
katı aynı zamanda 1,6'nın da katıdır. Program makul olan en büyük böleni seçer,
bu sıradan binalarda doğru ama çift yükseklikli zemin katı olan bir modelde
yanlıştır. Hiçbir grid çoğunluğu açıklamıyorsa uydurmak yerine hata verir.

Vermezsen bu iki sütun **hiç yazılmaz**. Sıfırla doldurmak yerine yok olmaları
kasıtlı: köprünün, makine parçasının, arazi yüzeyinin kat sayısı yoktur.

**Sadece `--keep-tags` verilirse:** okuyucunun kendi etiketleri sütuna
dönüşür — OBJ'de `USEMTL` / `G` / `O`, DXF'te `LAYER` / `ENTITY`. Bir blok
birden fazla değer kapsıyorsa en sık geçen yazılır.

⚠️ **Emsal hesabında `BASE_AREA × STOREYS` kullanma, `FLOOR_AREA` kullan.**
Çekme kat ana kütleden küçük olduğu için ikisi tutmaz. Örnek bir binada
328 × 6 = 1.968 m² çıkar ama gerçek değer (328 × 5) + (269 × 1) = 1.909 m².
4.116 binalık bir veri setinde bu fark 225.905 m²'ye ulaşıyor. `FLOOR_AREA`
bunu parça parça hesapladığı için doğru sonucu verir.

⚠️ **`CLOSED = false` olan feature'ların `VOLUME` değerine bakma** — zaten 0
yazılır. Açık bir yüzeyin kapalı hacmi tanımsızdır; uydurma bir sayı yazmak
yerine sıfırlanır. `CLOSED` alanını filtreleyerek bozuk geometrileri
bulabilirsin:

```
"CLOSED" = 0
```

Kapalılık testi **kaynaklanmış koordinat** üzerinden yapılır (0,1 mm
toleransla), vertex indeksi üzerinden değil. CAD ihracatçıları her yüzü kendi
vertex kopyalarıyla yazar — bir Rhino kutusu 8 değil 24 vertex ile gelir —
indeks bazlı test dosyadaki her katıyı "açık" sayardı.

`VOLUME`, bloğun kendi ağırlık merkezine göre integre edilir. Koordinat
orijinine göre yapılsaydı, projeksiyonlu bir CRS'te orijin milyonlarca metre
uzakta olduğu için terimler ~1e13, sonuç ~1e3 olurdu ve çıkarma anlamlı
basamakların çoğunu yerdi.

---

## Python API

### Tek çağrı

```python
import mesh2gis

n = mesh2gis.convert(
    "kutle.obj",
    "kutle.gpkg",
    up="y",  # None ise otomatik tahmin
    offset=(0.0, 0.0, 0.0),
    scale=1.0,
    group_by="usemtl",
    merge_stacks=True,
    epsg=5254,
    storey_height=3.2,
)
print(f"{n} feature yazıldı")
```

### Adım adım

Araya girip mesh'i incelemen gerektiğinde:

```python
import mesh2gis

mesh = mesh2gis.read_obj("kutle.obj")  # veya read("kutle.dxf")
print(mesh.n_vertices, mesh.n_faces, mesh.bounds())
print(mesh2gis.detect_up_axis(mesh))

mesh = mesh2gis.transform(mesh, up="y", offset=(436372.01, -4533303.26, 0.0))

blocks = mesh2gis.group(mesh, by="usemtl")
blocks = mesh2gis.merge_stacked(blocks, tolerance=0.05, overlap_ratio=0.3)

for i, b in enumerate(blocks[:5], start=1):
    a = mesh2gis.compute(b, i, storey_height=3.2)
    print(a.block_id, a.height, a.storeys, a.base_area, a.volume, a.closed)

mesh2gis.write_multipatch(blocks, "kutle.shp", epsg=5254, storey_height=3.2)
```

### Fonksiyon referansı

```python
read(path)                                          -> Mesh
read_obj(path, *, encoding="utf-8")                 -> Mesh
read_dxf(path, *, layers=None, extrude_thickness=True) -> Mesh

detect_up_axis(mesh)                                -> "y" | "z"
transform(mesh, *, up="z", offset=(0,0,0), scale=1.0) -> Mesh

group(mesh, by="usemtl", *, drop_empty=True)        -> list[Block]
merge_stacked(blocks, *, tolerance=0.05, overlap_ratio=0.3) -> list[Block]

compute(block, block_id, *, storey_height=None)     -> BlockAttrs

write_multipatch(blocks, path, *, epsg=None, storey_height=None) -> int
write_gpkg(blocks, path, *, epsg=None, layer="blocks", storey_height=None) -> int
write_obj(blocks, path, *, precision=6, header=None) -> int

wkt_for(epsg)                                       -> str
convert(source, target, *, up=None, offset=(0,0,0), scale=1.0,
        group_by="usemtl", merge_stacks=False, epsg=None,
        storey_height=None)                         -> int
```

### Veri tipleri

**`Mesh`** — `vertices` (`(N,3)` float64 numpy dizisi), `faces` (vertex indeks
dizilerinden oluşan liste), `tags` (`{"usemtl": [...], "g": [...], ...}`, her
biri yüz sayısı uzunluğunda). Yüzler `(F,3)` matrisi değil liste olarak
tutulur çünkü CAD çıktıları üçgen, dörtgen ve n-gon'u karıştırır.

**`Block`** — bir mesh'in yüz altkümesi. Vertex sahiplenmez, ana mesh'e indeks
verir; milyonlarca vertex'te gruplamanın ucuz kalması için. Alanlar: `mesh`,
`face_indices`, `label`. Metotlar: `bounds()`, `vertices()`,
`vertex_indices()`, `faces` (üreteç), `len()`.

**`BlockAttrs`** — `block_id`, `label`, `z_min`, `z_max`, `height`, `storeys`,
`base_area`, `volume`, `closed`, `n_faces`. `as_dict()` ile sözlüğe çevrilir.

### Hatalar

| İstisna | Ne zaman |
|---|---|
| `FileNotFoundError` | Girdi dosyası yok |
| `ValueError` | Bilinmeyen uzantı/strateji, boş etiket, geçersiz katman adı, sıfır ölçek, aralık dışı vertex indeksi |
| `ImportError` | DXF okunmak istendi ama `ezdxf` kurulu değil |
| `mesh2gis.UnknownCRSError` | EPSG kodu ne gömülü tabloda ne pyproj'da |

`UnknownCRSError` **yazmadan önce** fırlar — yarım kalmış, `.prj`'siz bir
shapefile bırakmaz.

---

## Tarifler

**Rhino'dan çıkmış kütle modeli, gerçek koordinatlı**

```bash
mesh2gis inspect model.obj --group-by usemtl
mesh2gis convert model.obj model.shp --up y --group-by usemtl \
    --epsg 5254 --storey-height 3.2
```

**Bina bazında tek feature ve toplam kat sayısı**

```bash
mesh2gis convert model.obj bina.gpkg --up y --group-by usemtl \
    --merge-stacks --epsg 5254 --storey-height 3.2
```

**AutoCAD DXF, thickness ile ekstrüde edilmiş binalar**

```bash
pip install 'mesh2gis[dxf]'
mesh2gis inspect halihazir.dxf --group-by layer
mesh2gis convert halihazir.dxf bina.shp --group-by layer --epsg 5254
```

Sadece belirli katmanları almak için Python tarafını kullan:

```python
mesh = mesh2gis.read_dxf("halihazir.dxf", layers=["BINA", "YAPI"])
```

**Milimetre biriminde model**

```bash
mesh2gis convert model.obj model.shp --up y --scale 0.001 --epsg 5254
```

**Etiketsiz mesh**

```bash
mesh2gis inspect model.obj --group-by connected
mesh2gis convert model.obj model.shp --group-by connected --epsg 5254
```

**Sadece temizlik — CAD'e geri götürmek için**

```bash
mesh2gis convert kirli.obj temiz.obj --up y --group-by usemtl
```

**Toplu işleme**

```python
from pathlib import Path
import mesh2gis

for src in Path("modeller").glob("*.obj"):
    n = mesh2gis.convert(
        src,
        src.with_suffix(".shp"),
        up="y",
        group_by="usemtl",
        epsg=5254,
        storey_height=3.2,
    )
    print(f"{src.name}: {n} feature")
```

---

## Sorun giderme

**Tek bir dev feature çıktı**
Gruplama stratejisi tutmamış. `mesh2gis inspect dosya.obj` çalıştır, `tags`
bölümüne bak, `distinct` sayısı 1'den büyük olan etiketi seç. Hepsi `absent`
ise `--group-by connected`.

**Model yan yatmış**
`--up` yanlış. Otomatik tahmin tek kule / tek ada modellerinde şaşar.
`--up y` ile `--up z`'yi dene, `inspect`'in `bounds` çıktısında yükseklik
span'inin makul (10–100 m) çıktığı doğrudur.

**Model haritanın yanlış yerinde**
Ya `--offset` eksik (model lokal koordinatta) ya da `--epsg` yanlış datum.
`inspect`'in `bounds` satırındaki sayılar 0 civarındaysa öteleme, TM
büyüklüğündeyse datum sorunu.

**ArcGIS'te hiçbir şey görünmüyor**
Map'e değil **Local Scene**'e atman gerekiyor. Multipatch 3B geometridir.

**Bina yüzeyleri içten görünüyor / gölgelendirme ters**
Kaynak modelde yüz sarımı tutarsız. mesh2gis sarımı korur, düzeltmez —
Rhino/Blender'da normalleri birleştirip yeniden ihraç et.

**`VOLUME` sıfır**
`CLOSED = 0` demektir; blok kapalı bir katı değil. Kütle modelinde alt veya üst
yüzü eksik bırakılmış objelerde olur. Yükseklik ve taban alanı yine doğrudur.

**`STOREYS` hep 0**
`--storey-height` vermemişsin. `inspect`'in `hint` satırı doğru değeri önerir.

**`UnknownCRSError`**
EPSG kodu gömülü tabloda yok. `pip install 'mesh2gis[crs]'` veya `--epsg`
vermeden çevirip ArcGIS/QGIS'te Define Projection ile tanımla.

**QGIS `.gpkg`'yi açıyor ama 3B görünmüyor**
Katman özelliklerinde 3B görünümü açman gerekiyor; geometri MultiPolygonZ
olarak doğru yazılmıştır. `.gpkg`'yi doğrulamak için:
`ogrinfo -so dosya.gpkg blocks`

**Büyük dosyada bellek yetmiyor**
Vertex dizisi bellekte tutulur; 400 bin vertex ~10 MB. Fotogrametri mesh'leri
(milyonlarca vertex) için bu paket doğru araç değil — ArcGIS'in kendi
`Import 3D Files` aracını kullan.

---

## Bilinen sınırlar

- **Texture, malzeme, LOD desteği yok.** Kaplamasız kütle modelleri için bir
  kayıp değil; kaplamalı fotogrametri mesh'i için bu paketi kullanma.
- **Scene layer (SLPK / I3S) çıktısı yok.** ArcGIS'te paylaşım için önce
  multipatch üret, sonra Pro'da Create 3D Object Scene Layer Content çalıştır.
- **`.obj` çıktısı geri okumada hassasiyet kaybeder.** Pek çok OBJ okuyucu
  float32 kullanır; 4,5 milyon büyüklüğündeki bir northing'de bu yarım metreye
  yuvarlanır. Shapefile ve GeoPackage float64 saklar. `.obj` çıktısını ölçüm
  için değil CAD'e geri dönüş için kullan.
- **`merge_stacked` sezgiseldir.** Yukarıdaki uyarıya bak.
- **Döndürme yapmaz.** Sadece eksen çevirme, ölçek ve öteleme.
- **Shapefile alan adları 10 karakterle sınırlı** (dBASE kuralı) ve `LABEL`
  alanı 64 karakterde kırpılır.
