# Basic Transformer implementation for MT

## Clients

Preprocess:
* `learnBPE_cli` : Learns BPE model
* `buildVOC_cli` : Builds vocabulary
* `tokenTXT_cli` : Tokenizes raw data

Network:
* `create_cli` : Creates network
* `learn_cli` : Runs learning 
* `translate_cli`: Runs inference

## Usage example:

Given train/valid/test raw (untokenized) datasets:

`$TRAIN`, `$VALID` and `$TEST` indicate the suffix of the respective (train/valid/test) datasets files while `$SS`/`$TT` indicate file extensions for source/target data.


### (1) Preprocess

* Build `$BPE` Model:

```
cat $TRAIN.{$SS,$TT} | python3 learnBPE_cli.py $BPE
```
A single BPE model is built for source and target sides of parallel data. Default number of symbols is 32,000.
BPE learning is computed after tokenizing input files following (`mode: aggressive, joiner_annotate: True, segment_numbers: True`).

* Create `$TOK` (tokenization config file) containing:

```
mode: aggressive
joiner_annotate: True
segment_numbers: True
bpe_model_path: $BPE
```

All network input/output files are tokenized/detokenized following this configuration.

* Build Vocabularies:

```
cat $TRAIN.$SS | python3 buildVOC_cli.py -tokenizer_config $TOK -max_size 32768 > $VOC.$SS
cat $TRAIN.$TT | python3 buildVOC_cli.py -tokenizer_config $TOK -max_size 32768 > $VOC.$TT
```

Vocabulries are computed after tokenizing files following `$TOK`. Vocabularies contain at most `32,768` tokens

### (2) Create network

```
python3 ./create_cli.py -dnet $DNET -src_vocab $VOC.$SS -tgt_vocab $VOC.$TT -src_token $TOK -tgt_token $TOK
```

Creates $DNET directory and copies files: network, src_voc, tgt_voc, src_tok, tgt_tok, src_bpe, tgt_bpe. Default network options are:
```
-emb_dim  512
-qk_dim   64
-v_dim    64
-ff_dim   2048
-n_heads  8
-n_layers 6
-dropout  0.1
```

Check network options in `$DNET/network`

### (3) Learning
```
python3 ./train_cli.py -dnet $DNET -src_train $TRAIN.$SS -tgt_train $TRAIN.$TT -src_valid $VALID.$SS -tgt_valid $VALID.$TT
```

Starts or continues learning using the given training/validation files. Default learning options are:
```
-max_steps      0 (infinite)
-max_epochs     0 (infinite)
-validate_every 5000
-save_every     5000
-report_every   100
-keep_last_n    10
-clip_grad_norm 0.0 (not clipped)
```
```
-lr              2.0
-min_lr          0.0001
-beta1           0.9
-beta2           0.998
-eps             1e-09
-noam_scale      2.0
-noam_warmup     4000
-label_smoothing 0.1
-loss            KLDiv
```
```
-shard_size 1000000
-max_length 100
-batch_size 4096
-batch_type tokens
```

### (4) Inference
```
python3 ./translate_cli.py -dnet $DNET -i $TEST.$SS
```

Translates the given input file using the last network checkpoint in `$DNET` directory. Default inference options are:
```
-beam_size 4
-n_best    1
-max_size  250
-alpha     0.0 (not used)
-format    iH
```
```
-shard_size 0 (single shared)
-max_length 0 (do not filter longer sentences)
-batch_size 30
-batch_type sentences
```

Option -format is used to specify the fields output for every example (TAB-separated):
```
[i] index in test set (sentences are sorted to minimize padding)
[n] rank in n-best
[c] global hypothesis cost
[s] source sentence
[S] source sentence (detokenised)
[u] source indexes
[h] hypothesis
[H] hypothesis (detokenised)
[v] hypothesis indexes
```



