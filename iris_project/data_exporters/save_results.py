# Import Mage's decorator only if it isn't already loaded
if 'data_exporter' not in globals():
    from mage_ai.data_preparation.decorators import data_exporter


# data_exporter marks this as a step that sends data out of the pipeline
# 'df' is the 30 predicted rows returned by train_model, passed in automatically by Mage
# It saves them to a CSV file and returns nothing, because this is an end of the pipeline
@data_exporter
def export_data(df, *args, **kwargs):
    df.to_csv('iris_predictions.csv', index=False)
    print('Saved', len(df), 'predictions to iris_predictions.csv')
