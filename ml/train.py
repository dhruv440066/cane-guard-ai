"""Train the sugarcane disease CNN (MobileNetV2 transfer learning).
Examples (run from the project root):
  python ml/train.py --download                      # downloads akilesh253/sugarcane-plant-diseases-dataset via kagglehub
  python ml/train.py --data "C:\\path\\to\\dataset"   # any folder containing class folders (or train/val/test folders)
Outputs in backend/models: model.keras, class_names.json, metrics.json, confusion_matrix.png, training_curves.png"""
import argparse, json, sys, pathlib, numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from data_utils import find_root, collect, make_splits
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_class_weight
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import tensorflow as tf

ap = argparse.ArgumentParser()
ap.add_argument("--data"); ap.add_argument("--download", action="store_true")
ap.add_argument("--epochs", type=int, default=12); ap.add_argument("--finetune-epochs", type=int, default=6); ap.add_argument("--size", type=int, default=224)
a = ap.parse_args()
if a.download:
    import kagglehub; a.data = kagglehub.dataset_download("akilesh253/sugarcane-plant-diseases-dataset"); print("Downloaded to:", a.data)
if not a.data or not pathlib.Path(a.data).exists(): sys.exit("Give an existing folder with --data, or use --download.")
tf.keras.utils.set_random_seed(42)
root, mode = find_root(a.data); classes, data, bad = collect(root, mode)
print(f"Dataset root: {root} ({mode})\nClasses: {classes}\nUnreadable images skipped: {len(bad)}")
tr, va, te = make_splits(data)
for n, s in [("train", tr), ("val", va), ("test", te)]:
    print(n, len(s), {classes[k]: sum(1 for _, l in s if l == k) for k in range(len(classes))})
S = (a.size, a.size)
def ds(items, training):
    d = tf.data.Dataset.from_tensor_slices(([p for p, _ in items], [l for _, l in items]))
    if training: d = d.shuffle(len(items), seed=42)
    def load(p, l):
        im = tf.io.decode_image(tf.io.read_file(p), channels=3, expand_animations=False)
        im = tf.image.resize(im, S); im.set_shape(S + (3,)); return im, l
    return d.map(load, num_parallel_calls=tf.data.AUTOTUNE).batch(32).prefetch(tf.data.AUTOTUNE)
dtr, dva, dte = ds(tr, True), ds(va, False), ds(te, False)
cw = dict(enumerate(compute_class_weight("balanced", classes=np.arange(len(classes)), y=[l for _, l in tr])))

aug = tf.keras.Sequential([tf.keras.layers.RandomFlip("horizontal_and_vertical"), tf.keras.layers.RandomRotation(0.1), tf.keras.layers.RandomZoom(0.1), tf.keras.layers.RandomBrightness(0.1)])
base = tf.keras.applications.MobileNetV2(input_shape=S + (3,), include_top=False, weights="imagenet"); base.trainable = False
i = tf.keras.Input(S + (3,)); x = aug(i); x = tf.keras.applications.mobilenet_v2.preprocess_input(x)
x = tf.keras.layers.GlobalAveragePooling2D()(base(x, training=False)); x = tf.keras.layers.Dropout(0.3)(x)
m = tf.keras.Model(i, tf.keras.layers.Dense(len(classes), activation="softmax")(x))
cb = [tf.keras.callbacks.EarlyStopping(patience=4, restore_best_weights=True, monitor="val_accuracy")]
m.compile(tf.keras.optimizers.Adam(1e-3), "sparse_categorical_crossentropy", metrics=["accuracy"])
h1 = m.fit(dtr, validation_data=dva, epochs=a.epochs, class_weight=cw, callbacks=cb)
base.trainable = True
for l in base.layers[:-30]: l.trainable = False
m.compile(tf.keras.optimizers.Adam(1e-5), "sparse_categorical_crossentropy", metrics=["accuracy"])
h2 = m.fit(dtr, validation_data=dva, epochs=a.finetune_epochs, class_weight=cw, callbacks=cb)

y = np.array([l for _, l in te]); p = m.predict(dte).argmax(1)
out = pathlib.Path(__file__).parent.parent / "backend/models"; out.mkdir(parents=True, exist_ok=True)
m.save(out / "model.keras"); (out / "class_names.json").write_text(json.dumps(classes))
try:
    converter = tf.lite.TFLiteConverter.from_keras_model(m)
    tflite_model = converter.convert()
    (out / "model.tflite").write_bytes(tflite_model)
    print("Exported TFLite model to", out / "model.tflite")
except Exception as ex:
    print("TFLite export notice:", ex)
rep = classification_report(y, p, target_names=classes, output_dict=True, zero_division=0); cm = confusion_matrix(y, p)
(out / "metrics.json").write_text(json.dumps({"report": rep, "confusion_matrix": cm.tolist(), "test_images": int(len(y))}, indent=1))
acc = h1.history["accuracy"] + h2.history["accuracy"]; vac = h1.history["val_accuracy"] + h2.history["val_accuracy"]
plt.figure(); plt.plot(acc, label="train"); plt.plot(vac, label="val"); plt.legend(); plt.xlabel("epoch"); plt.ylabel("accuracy"); plt.savefig(out / "training_curves.png", dpi=120)
plt.figure(figsize=(6, 5)); plt.imshow(cm, cmap="Greens"); plt.xticks(range(len(classes)), classes, rotation=45, ha="right"); plt.yticks(range(len(classes)), classes)
for r in range(len(classes)):
    for c in range(len(classes)): plt.text(c, r, cm[r, c], ha="center", va="center")
plt.tight_layout(); plt.savefig(out / "confusion_matrix.png", dpi=120)
print(classification_report(y, p, target_names=classes, zero_division=0)); print("Test accuracy:", rep["accuracy"]); print("Saved model to", out)
