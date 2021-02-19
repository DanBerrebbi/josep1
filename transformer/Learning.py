# -*- coding: utf-8 -*-

import sys
import os
import logging
import numpy as np
import torch
import time
from torch.utils.tensorboard import SummaryWriter
from transformer.Model import save_checkpoint, prepare_source, prepare_target

##############################################################################################################
### Score ####################################################################################################
##############################################################################################################

class Score():
  def __init__(self):
    #global
    self.nsteps = 0
    self.loss = 0.
    self.ntoks = 0
    self.nok = 0
    self.msec_epoch = time.time()
    #report
    self.loss_report = 0.
    self.nok_report = 0
    self.ntoks_report = 0
    self.nsteps_report = 0
    self.msec_report = self.msec_epoch

  def nOK(self, gold, pred, idx_pad):
    hyps = torch.nn.functional.log_softmax(pred, dim=-1) #[bs*lt, Vt]
    _, inds = torch.topk(hyps, k=1, dim=-1) #[bs*lt,1]
    inds = inds.squeeze(-1) #[bs*lt]
    nok = torch.sum(torch.logical_and((gold!=idx_pad), (inds==gold))) #sum(gold_is_not_pad AND inds_is_gold)
    return nok.item()

  def step(self, sum_loss_batch, gold, pred, idx_pad):
    #gold is [bs, lt]
    #pred is [bs, lt, Vt]

    gold = gold.contiguous().view(-1) #[bs*lt]
    pred = pred.contiguous().view(-1,pred.size(2)) #[bs*lt, Vt]
    nok_batch = self.nOK(gold,pred,idx_pad)

    ntoks_batch = torch.sum(gold != idx_pad)
    #global
    self.nsteps += 1
    self.loss += sum_loss_batch
    self.nok += nok_batch
    self.ntoks += ntoks_batch
    #report
    self.loss_report += sum_loss_batch
    self.nok_report += nok_batch
    self.ntoks_report += ntoks_batch
    self.nsteps_report += 1

  def report(self):
    tnow = time.time()
    if self.ntoks_report and self.nsteps_report:
      #print('Report loss={:.5f} ntoks={}'.format(self.loss_report, self.ntoks_report))
      loss_per_tok = self.loss_report / (1.0*self.ntoks_report)
      acc_per_tok = self.nok_report / (1.0*self.ntoks_report)
      ms_per_step = 1000.0 * (tnow - self.msec_report) / (1.0*self.nsteps_report)
    else:
      loss_per_tok = 0.
      acc_per_tok = 0.
      ms_per_step = 0.
      logging.warning('Requested report after 0 tokens optimised')
    #initialize for next report
    self.loss_report = 0.
    self.ntoks_report = 0
    self.nok_report = 0
    self.nsteps_report = 0
    self.msec_report = tnow
    return acc_per_tok, loss_per_tok, ms_per_step

  def epoch(self):
    tnow = time.time()
    if self.ntoks and self.nsteps:
      loss_per_tok = self.loss / (1.0*self.ntoks)
      acc_per_tok = self.nok / (1.0*self.ntoks)
      ms_epoch = 1000.0 * (tnow - self.msec_epoch)
    else:
      loss_per_tok = 0.
      acc_per_tok = 0.
      ms_epoch = 0.
      logging.warning('Requested epoch report after 0 tokens optimised')
    #no need to initialize
    return acc_per_tok, loss_per_tok, ms_epoch

##############################################################################################################
### Learning #################################################################################################
##############################################################################################################

class Learning():
  def __init__(self, model, optScheduler, criter, suffix, idx_pad, ol):
    super(Learning, self).__init__()
    self.model = model
    self.optScheduler = optScheduler
    self.criter = criter #LabelSmoothing+KLDivLoss or NLLLoss
    self.suffix = suffix
    self.max_steps = ol.max_steps
    self.max_epochs = ol.max_epochs
    self.validate_every = ol.validate_every
    self.save_every = ol.save_every
    self.report_every = ol.report_every
    self.keep_last_n = ol.keep_last_n
    self.clip_grad_norm = ol.clip_grad_norm
    self.idx_pad = idx_pad
    self.writer = SummaryWriter(log_dir=ol.dnet, comment='', purge_step=None, max_queue=10, flush_secs=60, filename_suffix='')

  def learn(self, trainset, validset, device):
    logging.info('Running: learning')
    n_epoch = 0
    while True: #repeat epochs
      n_epoch += 1
      logging.info('Epoch {}'.format(n_epoch))
      n_batch = 0
      score = Score()
      for batch_pos, batch_src, batch_tgt in trainset:
        n_batch += 1
        self.model.train()
        ### forward
        src, msk_src = prepare_source(batch_src, self.idx_pad, device)
        tgt, ref, msk_tgt = prepare_target(batch_tgt, self.idx_pad, device)
        pred = self.model.forward(src, tgt, msk_src, msk_tgt) #no log_softmax is applied
        ### compute loss
        loss_batch = self.criter(pred, ref) #sum of losses in batch
        loss_token = loss_batch / torch.sum(ref != self.idx_pad)
        ### optimize
        self.optScheduler.optimizer.zero_grad()                                        ### sets gradients to zero
        #loss_batch.backward()                                                         ### computes gradients
        loss_token.backward()                                                          ### computes gradients
        if self.clip_grad_norm > 0.0:
          torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.clip_grad_norm) ### clip gradients to clip_grad_norm
        self.optScheduler.step()                                                       ### updates model parameters after incrementing step and updating lr
        ### accumulate score
        score.step(loss_batch.item(), ref, pred, self.idx_pad)

        if self.report_every and self.optScheduler._step % self.report_every == 0: ### report
          acc_per_tok, loss_per_tok, ms_per_step = score.report()
          logging.info('Learning step: {} epoch: {} batch: {} steps/sec: {:.2f} lr: {:.6f} Acc: {:.3f} Loss: {:.3f}'.format(self.optScheduler._step, n_epoch, n_batch, 1000.0/ms_per_step, self.optScheduler._rate, acc_per_tok, loss_per_tok))
          #self.writer.add_scalar('Loss/train', loss_per_tok, self.optScheduler._step)
          self.writer.add_scalar('Loss/train', loss_token.item(), self.optScheduler._step)
          self.writer.add_scalar('LearningRate', self.optScheduler._rate, self.optScheduler._step)

        if self.validate_every and self.optScheduler._step % self.validate_every == 0: ### validate
          if validset is not None:
            vloss = self.validate(validset, device)

        if self.save_every and self.optScheduler._step % self.save_every == 0: ### save
          save_checkpoint(self.suffix, self.model, self.optScheduler.optimizer, self.optScheduler._step, self.keep_last_n)

        if self.max_steps and self.optScheduler._step >= self.max_steps: ### stop by max_steps
          if validset is not None:
            vloss = self.validate(validset, device)
          save_checkpoint(self.suffix, self.model, self.optScheduler.optimizer, self.optScheduler._step, self.keep_last_n)
          logging.info('Learning STOP by [steps={}]'.format(self.optScheduler._step))
          return

      acc_per_tok, loss_per_tok, ms_epoch = score.epoch()
      logging.info('EndOfEpoch: {} #batchs: {} Acc: {:.3f} Loss: {:.3f} sec: {:.2f}'.format(n_epoch,n_batch,acc_per_tok,loss_per_tok,ms_epoch/1000.0))

      if self.max_epochs and n_epoch >= self.max_epochs: ### stop by max_epochs
        if validset is not None:
          vloss = self.validate(validset, device)
        save_checkpoint(self.suffix, self.model, self.optScheduler.optimizer, self.optScheduler._step, self.keep_last_n)
        logging.info('Learning STOP by [epochs={}]'.format(n_epoch))
        return
    return

  def validate(self, validset, device):
    tic = time.time()
    valid_loss = 0.
    n_batch = 0
    with torch.no_grad():
      self.model.eval()
      for batch_pos, batch_src, batch_tgt in validset:
        n_batch += 1
        src, msk_src = prepare_source(batch_src, self.idx_pad, device)
        tgt, ref, msk_tgt = prepare_target(batch_tgt, self.idx_pad, device)
        pred = self.model.forward(src, tgt, msk_src, msk_tgt) #no log_softmax is applied
        loss = self.criter(pred, ref) ### batch loss
        valid_loss += loss.item() / torch.sum(ref != self.idx_pad)
        if n_batch == 1:
          print_pos_src_tgt_hyp_ref(pred[0], batch_pos[0], src[0], tgt[0], ref[0])

    toc = time.time()
    loss = 1.0*valid_loss/n_batch if n_batch else 0.0
    logging.info('Validation step: {} #batchs: {} sec: {:.2f} loss: {:.3f}'.format(self.optScheduler._step, n_batch, toc-tic, loss))
    self.writer.add_scalar('Loss/valid', loss, self.optScheduler._step)
    return loss

def print_pos_src_tgt_hyp_ref(pred, pos, src, tgt, ref):
  hyp = torch.nn.functional.log_softmax(pred, dim=-1) #[lt, vt]
  _, ind = torch.topk(hyp, k=1, dim=-1) #[lt,1]
  logging.info('POS: {}'.format(pos))
  logging.info('SRC: ' + ' '.join(['{: ^5}'.format(t) for t in src.tolist()]))
  logging.info('TGT: ' + ' '.join(['{: ^5}'.format(t) for t in tgt.tolist()]))
  logging.info('HYP: ' + ' '.join(['{: ^5}'.format(t) for t in ind.squeeze(-1).tolist()]))
  logging.info('REF: ' + ' '.join(['{: ^5}'.format(t) for t in ref.tolist()]))








