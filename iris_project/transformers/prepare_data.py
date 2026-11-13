import pandas as pd
from sklearn.model_selection import train_test_split


def _identity_decorator(function):
    return function


# Import Mage's decorators only if they aren't already loaded
if 'transformer' not in globals():
    try:
        from mage_ai.data_preparation.decorators import transformer
    except ModuleNotFoundError as exc:
        if exc.name != 'mage_ai':
            raise
        transformer = _identity_decorator
if 'test' not in globals():
    try:
        from mage_ai.data_preparation.decorators import test
    except ModuleNotFoundError as exc:
        if exc.name != 'mage_ai':
            raise
        test = _identity_decorator


# ransformer marks this as a step that changes data coming from an earlier block
# 'df' is the 150-row table returned by load_iris, passed in automatically by Mage
# It splits the data 80/20 and adds a 'split' column labelling each row train or test
@transformer
def transform(df, *args, **kwargs):
    train_df, test_df = train_test_split(df, test_size=0.3, random_state=42)

    train_df = train_df.copy()
    test_df = test_df.copy()
    train_df['split'] = 'train'
    test_df['split'] = 'test'

    result = pd.concat([train_df, test_df])
    print('Train rows:', len(train_df), '| Test rows:', len(test_df))
    return result


# Runs right after transform finishes, using its returned table as 'output'
# Checks that the new 'split' column was actually created
# If it's missing, the block fails and train_model never runs
@test
def test_output(output, *args):
    assert 'split' in output.columns, 'split column missing'
