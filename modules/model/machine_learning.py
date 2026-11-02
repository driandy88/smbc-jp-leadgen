import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import cross_val_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings("ignore")

# Optional imports - install if needed
try:
    import xgboost as xgb

    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("XGBoost not available. Install with: pip install xgboost")

try:
    import lightgbm as lgb

    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    print("LightGBM not available. Install with: pip install lightgbm")

try:
    import catboost as cb

    CATBOOST_AVAILABLE = True
except ImportError:
    CATBOOST_AVAILABLE = False
    print("CatBoost not available. Install with: pip install catboost")


def ml_experiment(X_train, X_test, y_train, y_test, random_state=42, scale_features=True, cv_folds=5):
    """
    Experiment with multiple ML models and return performance comparison matrix with confusion matrices.

    Parameters:
    -----------
    X_train, X_test : array-like or DataFrame
        Feature matrices for training and testing
    y_train, y_test : array-like or Series
        Target variables for training and testing
    test_size : float, default=0.2
        Proportion of dataset to include in test split (unused in this version)
    random_state : int, default=42
        Random state for reproducibility
    scale_features : bool, default=True
        Whether to scale features (recommended for SVM, KNN, Logistic Regression)
    cv_folds : int, default=5
        Number of cross-validation folds
    Returns:
    --------
    results_df : DataFrame
        Performance comparison matrix with metrics for each model
    trained_models : dict
        Dictionary of trained models
    confusion_matrices : dict
        Dictionary of confusion matrices for each model
    """

    # Scale features if requested
    if scale_features:
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
    else:
        X_train_scaled = X_train
        X_test_scaled = X_test

    # Initialize models
    models = {
        "Random Forest": RandomForestClassifier(n_estimators=100, random_state=random_state),
        "Decision Tree": DecisionTreeClassifier(random_state=random_state),
        "Logistic Regression": LogisticRegression(random_state=random_state, max_iter=1000),
        "KNN": KNeighborsClassifier(n_neighbors=5),
    }

    # Add gradient boosting models if available
    if XGBOOST_AVAILABLE:
        models["XGBoost"] = xgb.XGBClassifier(random_state=random_state, eval_metric="logloss")

    if LIGHTGBM_AVAILABLE:
        models["LightGBM"] = lgb.LGBMClassifier(random_state=random_state, verbose=-1)

    if CATBOOST_AVAILABLE:
        models["CatBoost"] = cb.CatBoostClassifier(random_state=random_state, verbose=False)

    # Store results
    results = []
    trained_models = {}
    confusion_matrices = {}

    print("Training models...")
    print("-" * 50)

    for name, model in models.items():
        print(f"Training {name}...")

        # Determine which data to use (scaled or original)
        if name in ["SVM", "Logistic Regression", "KNN"]:
            train_data = X_train_scaled
            test_data = X_test_scaled
        else:
            train_data = X_train
            test_data = X_test

        # Train the model
        model.fit(train_data, y_train)
        trained_models[name] = model

        # Make predictions
        y_pred = model.predict(test_data)

        # Calculate confusion matrix
        cm = confusion_matrix(y_test, y_pred)
        confusion_matrices[name] = cm

        # Calculate metrics
        accuracy = accuracy_score(y_test, y_pred)

        # Check if binary or multiclass classification
        unique_classes = np.unique(np.concatenate([y_train, y_test]))
        is_binary = len(unique_classes) == 2

        precision = precision_score(y_test, y_pred, average="binary")
        recall = recall_score(y_test, y_pred, average="binary")
        f1 = f1_score(y_test, y_pred, average="binary")

        # ROC-AUC (for binary classification or multiclass with probability)
        try:
            if is_binary:
                y_proba = model.predict_proba(test_data)[:, 1]
                roc_auc = roc_auc_score(y_test, y_proba)
            else:
                y_proba = model.predict_proba(test_data)
                roc_auc = roc_auc_score(y_test, y_proba, multi_class="ovr")
        except Exception as e:
            roc_auc = np.nan

        # Cross-validation score
        cv_data = X_train_scaled if name in ["SVM", "Logistic Regression", "KNN"] else X_train
        cv_scores = cross_val_score(model, cv_data, y_train, cv=cv_folds, scoring="f1")
        cv_mean = cv_scores.mean()
        cv_std = cv_scores.std()

        # Store results
        results.append(
            {
                "Model": name,
                "Accuracy": accuracy,
                "Precision": precision,
                "Recall": recall,
                "F1-Score": f1,
                "ROC-AUC": roc_auc,
                "CV_Mean": cv_mean,
                "CV_Std": cv_std,
            }
        )

        print(f"{name} - Accuracy: {accuracy:.4f}, F1: {f1:.4f}")

    # Create results DataFrame
    results_df = pd.DataFrame(results)
    results_df = results_df.round(4)
    results_df = results_df.sort_values("Accuracy", ascending=False).reset_index(drop=True)

    print("\n" + "=" * 70)
    print("EXPERIMENT RESULTS")
    print("=" * 70)
    print(results_df.to_string(index=False))

    return results_df, trained_models, confusion_matrices


# Helper function to visualize confusion matrices (optional)
def plot_confusion_matrices(confusion_matrices, figsize=(15, 10)):
    """
    Plot confusion matrices for all models using matplotlib/seaborn.

    Parameters:
    -----------
    confusion_matrices : dict
        Dictionary of confusion matrices from ml_experiment
    figsize : tuple, default=(15, 10)
        Figure size for the plot
    """
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError:
        print("matplotlib and seaborn required for plotting. Install with:")
        print("pip install matplotlib seaborn")
        return

    n_models = len(confusion_matrices)
    cols = 3
    rows = (n_models + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=figsize)
    if rows == 1:
        axes = axes.reshape(1, -1)

    for idx, (name, cm) in enumerate(confusion_matrices.items()):
        row = idx // cols
        col = idx % cols
        ax = axes[row, col]

        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=ax)
        ax.set_title(f"{name}")
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")

    # Hide empty subplots
    for idx in range(n_models, rows * cols):
        row = idx // cols
        col = idx % cols
        axes[row, col].set_visible(False)

    plt.tight_layout()
    plt.show()
