import joblib
from sklearn.tree import DecisionTreeClassifier

# Import Mage's decorators only if they aren't already loaded
if 'transformer' not in globals():
    from mage_ai.data_preparation.decorators import transformer
if 'test' not in globals():
    from mage_ai.data_preparation.decorators import test

# The 4 measurement columns the model uses to predict the species
FEATURES = ['sepal length (cm)', 'sepal width (cm)',
            'petal length (cm)', 'petal width (cm)']


# transformer receives prepare_data's table (150 rows with 'split') as 'df'
# Reads max_depth from Mage's pipeline variables, then trains a decision tree on the train rows
# Predicts the 30 test rows, prints accuracy, saves the model and returns the predictions
@transformer
def train(df, *args, **kwargs):
    max_depth = int(kwargs.get('max_depth', 3))

    train_df = df[df['split'] == 'train']
    test_df = df[df['split'] == 'test'].copy()

    model = DecisionTreeClassifier(max_depth=max_depth, random_state=42)
    model.fit(train_df[FEATURES], train_df['target'])

    test_df['predicted'] = model.predict(test_df[FEATURES])
    accuracy = (test_df['predicted'] == test_df['target']).mean()
    print('max_depth =', max_depth, '| Test accuracy =', round(accuracy, 3))

    joblib.dump(model, 'iris_model.pkl')
    return test_df


# Runs right after train finishes, using its 30 predicted rows as 'output'
# Recalculates accuracy by comparing 'predicted' with the true 'target'
# If accuracy is below 80%, the block fails and save_results / evaluate_model never run
@test
def test_accuracy(output, *args):
    accuracy = (output['predicted'] == output['target']).mean()
    assert accuracy >= 0.8, 'Model accuracy is below 80%'
