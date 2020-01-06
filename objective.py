import torch
import torch.nn as nn
import pdb

class LFADS_Loss(nn.Module):
    def __init__(self, loglikelihood,
                 kl_weight_init=0.0, l2_weight_init=0.0,
                 kl_weight_schedule_dur = 2000, l2_weight_schedule_dur = 2000,
                 kl_weight_schedule_start = 0, l2_weight_schedule_start = 0,
                 kl_weight_max=1.0, l2_weight_max=1.0,
                 l2_con_scale=0.0, l2_gen_scale=0.0):
        
        super(LFADS_Loss, self).__init__()
        self.loglikelihood = loglikelihood
        
        self.loss_weights = {'kl' : {'weight' : kl_weight_init,
                                     'schedule_dur' : kl_weight_schedule_dur,
                                     'schedule_start' : kl_weight_schedule_start,
                                     'max' : kl_weight_max,
                                     'min' : kl_weight_init},
                             'l2' : {'weight' : l2_weight_init,
                                     'schedule_dur' : l2_weight_schedule_dur,
                                     'schedule_start' : l2_weight_schedule_start,
                                     'max' : l2_weight_max,
                                     'min' : l2_weight_init}}

        self.l2_con_scale = l2_con_scale
        self.l2_gen_scale = l2_gen_scale
        
        
    def forward(self, x_orig, x_recon, model):
        kl_weight = self.loss_weights['kl']['weight']
        l2_weight = self.loss_weights['l2']['weight']
        
        recon_loss = -self.loglikelihood(x_orig.permute(1, 0, 2), x_recon.permute(1, 0, 2))

        kl_loss = kl_weight * kldiv_gaussian_gaussian(post_mu  = model.g_posterior_mean,
                                                      post_lv  = model.g_posterior_logvar,
                                                      prior_mu = model.g_prior_mean,
                                                      prior_lv = model.g_prior_logvar)
    
        l2_loss = l2_weight * self.l2_gen_scale * model.generator.gru_generator.hidden_weight_l2_norm()
    
        if hasattr(model, 'controller'):
            kl_loss += kl_weight * kldiv_gaussian_gaussian(post_mu  = model.u_posterior_mean,
                                                           post_lv  = model.u_posterior_logvar,
                                                           prior_mu = model.u_prior_mean,
                                                           prior_lv = model.u_prior_logvar)
            
            l2_loss += l2_weight * self.l2_con_scale * model.controller.gru_controller.hidden_weight_l2_norm()
            
        return recon_loss, kl_loss, l2_loss
    
    #------------------------------------------------------------------------------
    #------------------------------------------------------------------------------

    def weight_schedule_fn(self, step):
        '''
        weight_schedule_fn(step)
        
        Calculate the KL and L2 regularization weights from the current training step number. Imposes
        linearly increasing schedule on regularization weights to prevent early pathological minimization
        of KL divergence and L2 norm before sufficient data reconstruction improvement. See bullet-point
        4 of section 1.9 in online methods
        
        required arguments:
            - step (int) : training step number
        '''
        
        for key in self.loss_weights.keys():
            # Get step number of scheduler
            weight_step = max(step - self.loss_weights[key]['schedule_start'], 0)
            
            # Calculate schedule weight
            self.loss_weights[key]['weight'] = max(min(weight_step/ self.loss_weights[key]['schedule_dur'], self.loss_weights[key]['max']), self.loss_weights[key]['min'])
            
            
class LogLikelihoodPoisson(nn.Module):
    
    def __init__(self, dt=1.0, device='cpu'):
        super(LogLikelihoodPoisson, self).__init__()
        self.dt = dt
        
    def forward(self, k, lam):
#         pdb.set_trace()
        return loglikelihood_poisson(k, lam*self.dt)
    
def loglikelihood_poisson(k, lam):
    '''
    loglikelihood_poisson(k, lam)

    Log-likelihood of Poisson distributed counts k given intensity lam.

    Arguments:
        - k (torch.Tensor): Tensor of size batch-size x time-step x input dimensions
        - lam (torch.Tensor): Tensor of size batch-size x time-step x input dimensions
    '''
    return (k * torch.log(lam) - lam - torch.lgamma(k + 1)).mean(dim=0).sum()

def kldiv_gaussian_gaussian(post_mu, post_lv, prior_mu, prior_lv):
    '''
    kldiv_gaussian_gaussian(post_mu, post_lv, prior_mu, prior_lv)

    KL-Divergence between a prior and posterior diagonal Gaussian distribution.

    Arguments:
        - post_mu (torch.Tensor): mean for the posterior
        - post_lv (torch.Tensor): logvariance for the posterior
        - prior_mu (torch.Tensor): mean for the prior
        - prior_lv (torch.Tensor): logvariance for the prior
    '''
    klc = 0.5 * (prior_lv - post_lv + torch.exp(post_lv - prior_lv) \
         + ((post_mu - prior_mu)/torch.exp(0.5 * prior_lv)).pow(2) - 1.0).mean(dim=0).sum()
    return klc