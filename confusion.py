# -*- coding: utf-8 -*-
# @Author :Xiaoju
# Time : 2025/6/4 下午7:34
# -*- coding: utf-8 -*-
# @Author :Xiaoju
# Time    : 2025/4/9 下午11:26

import os
import numpy as np
import torch
import matplotlib.pyplot as plt
from sklearn.metrics import (
    precision_recall_curve,
    confusion_matrix,
    classification_report
)
from torchvision.utils import save_image
from tqdm import tqdm


def compute_best_thresholds(model, loader, device, num_classes=3, class_names=None):
    """
    计算各类最佳阈值（以 F1 最大化为准），仅打印最终阈值列表。
    """
    model.eval()
    all_scores, all_labels = [], []
    with torch.no_grad():
        for imgs, labels in loader:
            imgs = imgs.to(device)
            probs = torch.softmax(model(imgs), dim=1).cpu().numpy()
            all_scores.append(probs)
            all_labels.append(labels.numpy())

    y_score = np.vstack(all_scores)    # (N, C)
    y_true = np.hstack(all_labels)     # (N,)
    y_true_onehot = np.eye(num_classes)[y_true]

    best_thresh = []
    for i in range(num_classes):
        prec, recall, thresh = precision_recall_curve(y_true_onehot[:, i], y_score[:, i])
        f1 = 2 * prec * recall / (prec + recall + 1e-8)
        best_idx = np.argmax(f1[:-1])
        best_thresh.append(thresh[best_idx])

    # 仅打印各类最终阈值
    if class_names:
        for i, t in enumerate(best_thresh):
            print(f"Threshold[{class_names[i]}] = {t:.4f}")
    else:
        print("Best thresholds:", [f"{t:.4f}" for t in best_thresh])

    return best_thresh


def threshold_predict(probs, best_thresh):
    if isinstance(best_thresh, float):  # 处理二分类单阈值的情况
        return int(probs[-1] > best_thresh)
    else:  # 处理多分类多阈值的情况
        mask = [float(p) > float(t) for p, t in zip(probs, best_thresh)]
        if any(mask):
            return np.argmax(mask)
        else:
            return np.argmax(probs)

def plot_confusion(model, loader, device, out_png, class_names):
    """
    画混淆矩阵热力图（counts），能兼容 loader 返回 >2 个元素的情形。
    只会取 loader 返回的前两个元素 (imgs, labels)。
    """
    model.eval()
    all_preds = []
    all_labels = []

    # 如果 loader 返回的是 (imgs, labels, paths, masks)，这里只取 imgs, labels
    with torch.no_grad():
        for batch in tqdm(loader, desc="Computing confusion"):
            # batch 可能是 (imgs, labels) 或 (imgs, labels, paths) 或 (imgs, labels, paths, masks)
            imgs, labels = batch[0], batch[1]
            imgs = imgs.to(device)
            labels = labels.to(device)

            logits = model(imgs)
            preds = torch.argmax(logits, dim=1)

            all_preds.append(preds.cpu().numpy())
            all_labels.append(labels.cpu().numpy())

    y_true = np.concatenate(all_labels, axis=0)
    y_pred = np.concatenate(all_preds, axis=0)

    cm = confusion_matrix(y_true, y_pred)
    plt.figure(figsize=(6, 5))
    plt.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues)
    plt.title("Confusion Matrix (Counts)")
    plt.colorbar()
    tick_marks = np.arange(len(class_names))
    plt.xticks(tick_marks, class_names, rotation=45)
    plt.yticks(tick_marks, class_names)

    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            plt.text(j, i, format(cm[i, j], 'd'),
                     horizontalalignment="center",
                     color="white" if cm[i, j] > thresh else "black")

    plt.ylabel('True label')
    plt.xlabel('Predicted label')
    plt.tight_layout()
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    plt.savefig(out_png)
    plt.close()


def save_classification_report(model, loader, device, out_txt_path, best_thresh, class_names=None):
    """
    生成分类报告并保存，同时简要打印整体指标（每类 Precision/Recall/F1）。
    """
    model.eval()
    all_probs, all_labels = [], []
    with torch.no_grad():
        for imgs, labels in loader:
            imgs = imgs.to(device)
            logits = model(imgs)
            probs = torch.softmax(logits, dim=1).cpu().numpy()
            all_probs.append(probs)
            all_labels.append(labels.numpy())

    y_true = np.hstack(all_labels)
    y_score = np.vstack(all_probs)
    y_pred = np.array([threshold_predict(p, best_thresh) for p in y_score], dtype=int)

    report = classification_report(
        y_true, y_pred,
        target_names=(class_names if class_names else None),
        digits=4
    )
    os.makedirs(os.path.dirname(out_txt_path), exist_ok=True)
    with open(out_txt_path, 'w', encoding='utf-8') as f:
        f.write(report)

    # 打印每类 Precision/Recall/F1
    lines = report.strip().split("\n")
    print(f"\nClassification Report:\n")
    # 只打印前三行表头 + 每类一行 + 最后一行 avg/total
    # 打印表头（前两行）
    for ln in lines[:2]:
        print(ln)

    # 提取每类指标并格式化输出
    for cls in class_names if class_names else [f"Class{i}" for i in range(len(lines) - 4)]:
        for ln in lines:
            if ln.startswith(cls):
                # 分割行数据（假设用空格分隔）
                parts = [p for p in ln.split() if p]
                if len(parts) >= 5:  # 确保有足够的字段
                    # 格式化：类别左对齐，指标右对齐，保留两位小数
                    formatted_line = f"{parts[0]:<15} {float(parts[1]):>6.2f} {float(parts[2]):>6.2f} {float(parts[3]):>6.2f} {int(parts[4]):>6}"
                    print(formatted_line)
                else:
                    print(ln)  # 异常情况直接打印
                break

    print(lines[-1])  # 打印最后一行总体指标


def plot_multiclass_pr_curve(model, loader, device, out_path, num_classes=3, class_names=None):
    """
    绘制多类别 PR 曲线并保存，只打印每类 AUC≈area_under_curve(precision-recall) 估计值。
    """
    from sklearn.metrics import auc as sk_auc

    model.eval()
    all_scores, all_labels = [], []
    with torch.no_grad():
        for imgs, labels in loader:
            imgs = imgs.to(device)
            probs = torch.softmax(model(imgs), dim=1).cpu().numpy()
            all_scores.append(probs)
            all_labels.append(labels.numpy())

    y_score = np.vstack(all_scores)
    y_true = np.hstack(all_labels)
    y_true_onehot = np.eye(num_classes)[y_true]

    plt.figure(figsize=(8, 6))
    auc_list = []
    for i in range(num_classes):
        prec, recall, _ = precision_recall_curve(y_true_onehot[:, i], y_score[:, i])
        pr_auc = sk_auc(recall, prec)
        auc_list.append(pr_auc)
        label = class_names[i] if class_names else f"Class {i}"
        plt.plot(recall, prec, linewidth=2, label=f"{label} (AUC={pr_auc:.3f})")

    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title("Multi-class Precision-Recall Curve")
    plt.legend(loc="best")
    plt.grid(True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()

    # 打印每类 PR AUC
    print("\nPR AUC per class:")
    if class_names:
        for i, a in enumerate(auc_list):
            print(f"{class_names[i]:>10}: {a:.4f}")
    else:
        print([f"{a:.4f}" for a in auc_list])


def plot_loss_curve(train_losses, val_losses, out_path):
    """
    绘制 Train/Val Loss 曲线并保存，同时打印损失表格（Epoch/Train/Val）。
    """
    epochs = np.arange(1, len(train_losses) + 1)
    plt.figure(figsize=(8, 5))
    plt.plot(epochs, train_losses, label="Train Loss", marker='o')
    plt.plot(epochs, val_losses, label="Val Loss", marker='s')
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.title("Train vs. Val Loss Curve")
    plt.legend()
    plt.grid(True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()

    print("\nEpoch   TrainLoss   ValLoss")
    for e, (tr, vl) in enumerate(zip(train_losses, val_losses), start=1):
        print(f"{e:>3}    {tr:.4f}    {vl:.4f}")


def visualize_misclassified(model, loader, device, best_thresh, out_dir, class_names=None):
    """
    仅统计并打印每对 (true→pred) 的误分类数量，不再逐一列出索引。
    并保存误分类图片到对应子文件夹。
    """
    model.eval()
    os.makedirs(out_dir, exist_ok=True)
    num_classes = len(class_names) if class_names else 3
    for t in range(num_classes):
        for p in range(num_classes):
            if t != p:
                os.makedirs(os.path.join(out_dir, f"true_{t}_pred_{p}"), exist_ok=True)

    idx_counter = {}
    with torch.no_grad():
        for batch_idx, (imgs, labels) in enumerate(loader):
            imgs_device = imgs.to(device)
            logits = model(imgs_device)
            probs = torch.softmax(logits, dim=1).cpu().numpy()
            labels_np = labels.numpy()

            for i, (p, true_label) in enumerate(zip(probs, labels_np)):
                pred_label = threshold_predict(p, best_thresh)
                if pred_label != true_label:
                    key = (true_label, pred_label)
                    idx_counter[key] = idx_counter.get(key, 0) + 1

                    # 保存误分类图片
                    img_tensor = imgs[i]
                    # 扩展 mean 和 std 为 4 通道
                    mean = torch.tensor([0.485, 0.456, 0.406, 0]).view(4, 1, 1)
                    std  = torch.tensor([0.229, 0.224, 0.225, 1]).view(4, 1, 1)
                    img_unnorm = img_tensor * std + mean
                    img_unnorm = torch.clamp(img_unnorm, 0, 1)

                    save_path = os.path.join(
                        out_dir,
                        f"true_{true_label}_pred_{pred_label}",
                        f"{batch_idx}_{i}.png"
                    )
                    save_image(img_unnorm[:3], save_path)  # 只保存前 3 通道

    # 打印每对 (true→pred) 的误分类计数
    print("\nMisclassified counts (true→pred):")
    for (t, p), cnt in idx_counter.items():
        tname = class_names[t] if class_names else str(t)
        pname = class_names[p] if class_names else str(p)
        print(f"{tname:>10}→{pname:<10}: {cnt}")