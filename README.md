# Basic Transformer implementation for MT

## Clients

Preprocess:
* `learnBPE_cli` : Learns BPE model after applying tokenization ("aggressive", joiner_annotate=True, segment_numbers=True)
* `buildVOC_cli` : Builds vocabulary given tokenization
* `tokenTXT_cli` : Tokenizes raw data
* `buildIDX_cli` : Builds batches from raw data given tokenization and vocabularies

Network:
* `create_cli` : Creates network
* `learn_cli` : Runs learning 
* `translate_cli`: Runs inference

## Usage example:

Given train/valid/test datasets:

### (1) Preprocess

Build `$fBPE` Model:

```
cat $TRAINING.{$SS,$TT} | python3 learnBPE_cli.py $fBPE
```

Create tokenization config file `$fTOK`:

```
mode: aggressive
joiner_annotate: True
segment_numbers: True
bpe_model_path: $fBPE
```

Build Vocabularies:

```
cat $TRAIN.$SS | python3 buildVOC_cli.py -tokenizer_config $fTOK -max_size 32768 > $fVOC.$SS
cat $TRAIN.$TT | python3 buildVOC_cli.py -tokenizer_config $fTOK -max_size 32768 > $fVOC.$TT
```

### (2) Create network

```
python3 ./create_cli.py -dnet $DNET -src_vocab $fVOC.$SS -tgt_vocab $fVOC.$TT -src_token $fTOK -tgt_token $fTOK
```

### (3) Learning
```
python3 ./learn_cli.py -dnet $DNET -src_train $TRAIN.$SS -tgt_train $TRAIN.$TT -src_valid $VALID.$SS -tgt_valid $VALID.$TT
```

### (4) Inference
```
python3 ./translate_cli.py -dnet $DNET -i $TEST.$SS
```


