import numpy as np
import joblib
import json
import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import MinMaxScaler
from datetime import datetime

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Training on: {DEVICE}")
if DEVICE.type == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}")

MODEL_DIR = "models/lstm_forecaster"
os.makedirs(MODEL_DIR, exist_ok=True)

data = np.load("data/lstm_training_sequences.npz")
X, y = data["X"], data["y"]
print(f"Loaded: X={X.shape}, y={y.shape}")

n, w, c = X.shape
scaler = MinMaxScaler()
X_scaled = scaler.fit_transform(X.reshape(-1, c)).reshape(n, w, c)
y_scaled = scaler.transform(y.reshape(-1, c)).reshape(y.shape)

split = int(0.8 * n)
X_train = torch.tensor(X_scaled[:split], dtype=torch.float32)
y_train = torch.tensor(y_scaled[:split], dtype=torch.float32)
X_val   = torch.tensor(X_scaled[split:], dtype=torch.float32)
y_val   = torch.tensor(y_scaled[split:], dtype=torch.float32)

train_loader = DataLoader(TensorDataset(X_train, y_train),
                          batch_size=256, shuffle=True, pin_memory=True)
val_loader   = DataLoader(TensorDataset(X_val, y_val),
                          batch_size=256, shuffle=False, pin_memory=True)


class BiLSTMForecaster(nn.Module):
    def __init__(self, n_features=6, hidden=128, n_layers=2,
                 forecast_days=7, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features,
            hidden_size=hidden,
            num_layers=n_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout
        )
        self.bn = nn.BatchNorm1d(hidden * 2)
        self.fc1 = nn.Linear(hidden * 2, 64)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(64, forecast_days * n_features)
        self.forecast_days = forecast_days
        self.n_features = n_features

    def forward(self, x):
        out, _ = self.lstm(x)
        out = out[:, -1, :]          # last timestep
        out = self.bn(out)
        out = self.dropout(self.relu(self.fc1(out)))
        out = self.fc2(out)
        return out.view(-1, self.forecast_days, self.n_features)


model = BiLSTMForecaster(n_features=c).to(DEVICE)
optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer, patience=7, factor=0.5, verbose=True, min_lr=1e-5
)
criterion = nn.L1Loss()  # MAE loss

EPOCHS = 100
best_val_loss = float("inf")
patience_counter = 0
PATIENCE = 15
best_weights = None

print(f"\nTraining BiLSTM on {DEVICE} ({EPOCHS} epochs max)...")
for epoch in range(1, EPOCHS + 1):
    model.train()
    train_loss = 0.0
    for xb, yb in train_loader:
        xb, yb = xb.to(DEVICE), yb.to(DEVICE)
        optimizer.zero_grad()
        pred = model(xb)
        loss = criterion(pred, yb)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        train_loss += loss.item() * len(xb)
    train_loss /= len(X_train)

    model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for xb, yb in val_loader:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            val_loss += criterion(model(xb), yb).item() * len(xb)
    val_loss /= len(X_val)
    scheduler.step(val_loss)

    if epoch % 10 == 0 or epoch == 1:
        print(f"  Epoch {epoch:03d} | Train MAE: {train_loss:.4f} | Val MAE: {val_loss:.4f} | LR: {optimizer.param_groups[0]['lr']:.6f}")

    if val_loss < best_val_loss:
        best_val_loss = val_loss
        best_weights = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        patience_counter = 0
    else:
        patience_counter += 1
        if patience_counter >= PATIENCE:
            print(f"  Early stopping at epoch {epoch}")
            break

model.load_state_dict(best_weights)
model.eval()

# Evaluate MAE per category in original ₹ scale
all_preds, all_true = [], []
with torch.no_grad():
    for xb, yb in val_loader:
        pred = model(xb.to(DEVICE)).cpu().numpy()
        all_preds.append(pred)
        all_true.append(yb.numpy())

y_pred_scaled = np.concatenate(all_preds)
y_true_scaled = np.concatenate(all_true)
y_pred = scaler.inverse_transform(y_pred_scaled.reshape(-1, c)).reshape(y_pred_scaled.shape)
y_true = scaler.inverse_transform(y_true_scaled.reshape(-1, c)).reshape(y_true_scaled.shape)

CATEGORIES = ["Food & Dining", "Transport", "Shopping",
              "Entertainment", "Utilities & Bills", "Groceries"]
mae_per_cat = np.mean(np.abs(y_pred - y_true), axis=(0, 1))
print("\nFinal MAE per category (₹):")
for cat, mae in zip(CATEGORIES, mae_per_cat):
    status = "✅" if mae < 300 else "⚠️"
    print(f"  {status} {cat}: ₹{mae:.1f}")

# Save model weights + architecture config
torch.save({
    "model_state_dict": best_weights,
    "model_config": {
        "n_features": c,
        "hidden": 128,
        "n_layers": 2,
        "forecast_days": 7,
        "dropout": 0.2
    }
}, f"{MODEL_DIR}/model.pt")

joblib.dump(scaler, f"{MODEL_DIR}/scaler.joblib")
with open(f"{MODEL_DIR}/categories.json", "w") as f:
    json.dump(CATEGORIES, f)
with open(f"{MODEL_DIR}/metadata.json", "w") as f:
    json.dump({
        "trained_at": datetime.utcnow().isoformat(),
        "framework": "PyTorch",
        "architecture": "BiLSTM(128x2) + BN + Dense(64)",
        "trained_on": str(DEVICE),
        "best_val_mae": round(float(best_val_loss), 4),
        "categories": CATEGORIES,
        "mae_per_category": {
            cat: round(float(m), 2)
            for cat, m in zip(CATEGORIES, mae_per_cat)
        }
    }, f, indent=2)

print(f"\n✅ PyTorch BiLSTM saved → {MODEL_DIR}/model.pt")