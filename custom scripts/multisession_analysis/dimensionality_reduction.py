import numpy as np
import matplotlib.pyplot as plt
from sklearn.datasets import fetch_openml
import standard_pipeline.place_cell_pipeline as pipe
from sklearn.decomposition import PCA
import plotly.express as px
import plotly.io as pio
import pandas as pd
import seaborn as sns
from sklearn.manifold import TSNE
from scipy import signal
from mne.time_frequency import psd_array_multitaper

#%% NMA PCA functions

def change_of_basis(X, W):
    """
    Projects data onto a new basis.

    Args:
      X (numpy array of floats) : Data matrix each column corresponding to a
                                  different random variable
      W (numpy array of floats) : new orthonormal basis columns correspond to
                                  basis vectors

    Returns:
      (numpy array of floats)   : Data matrix expressed in new basis
    """

    Y = np.matmul(X, W)

    return Y


def get_sample_cov_matrix(X):
    """
    Returns the sample covariance matrix of data X.

    Args:
      X (numpy array of floats) : Data matrix each column corresponds to a
                                  different random variable

    Returns:
      (numpy array of floats)   : Covariance matrix
  """

    X = X - np.mean(X, 0)
    cov_matrix = 1 / X.shape[0] * np.matmul(X.T, X)
    return cov_matrix


def sort_evals_descending(evals, evectors):
    """
    Sorts eigenvalues and eigenvectors in decreasing order. Also aligns first two
    eigenvectors to be in first two quadrants (if 2D).

    Args:
      evals (numpy array of floats)    :   Vector of eigenvalues
      evectors (numpy array of floats) :   Corresponding matrix of eigenvectors
                                           each column corresponds to a different
                                           eigenvalue

    Returns:
      (numpy array of floats)          : Vector of eigenvalues after sorting
      (numpy array of floats)          : Matrix of eigenvectors after sorting
    """

    index = np.flip(np.argsort(evals))
    evals = evals[index]
    evectors = evectors[:, index]
    if evals.shape[0] == 2:
        if np.arccos(np.matmul(evectors[:, 0],
                               1 / np.sqrt(2) * np.array([1, 1]))) > np.pi / 2:
            evectors[:, 0] = -evectors[:, 0]
        if np.arccos(np.matmul(evectors[:, 1],
                               1 / np.sqrt(2) * np.array([-1, 1]))) > np.pi / 2:
            evectors[:, 1] = -evectors[:, 1]

    return evals, evectors


def pca(X):
    """
    Performs PCA on multivariate data. Eigenvalues are sorted in decreasing order

    Args:
       X (numpy array of floats) :   Data matrix each column corresponds to a
                                     different random variable

    Returns:
      (numpy array of floats)    : Data projected onto the new basis
      (numpy array of floats)    : Vector of eigenvalues
      (numpy array of floats)    : Corresponding matrix of eigenvectors

    """

    X = X - np.mean(X, 0)
    cov_matrix = get_sample_cov_matrix(X)
    evals, evectors = np.linalg.eigh(cov_matrix)
    evals, evectors = sort_evals_descending(evals, evectors)
    score = change_of_basis(X, evectors)

    return score, evectors, evals


def prepare_data(pcf):
    # Neurons as samples, position bins as features
    raw_data = pcf.bin_avg_activity
    pc_idx = [x[0] for x in pcf.place_cells]
    labels = np.zeros(len(raw_data))
    labels[pc_idx] = 1

    # Standardize (z-score) data
    data = (raw_data - np.mean(raw_data, axis=0)) / np.std(raw_data, axis=0)
    return data, labels


def perform_pca(pcf):

    data, labels = prepare_data(pcf)
    n_features = pcf.params['n_bins']
    # Perform PCA
    pca_model = PCA(n_components=n_features)  # Initializes PCA
    out = pca_model.fit(data)  # Performs PCA

    return data, np.array(labels, dtype=bool), pca_model


def perform_tsne(pcf, perplexity=50):

    data, labels = prepare_data(pcf)

    tsne_mod = TSNE(n_components=2, perplexity=perplexity, n_iter=5000)
    embed = tsne_mod.fit_transform(data)

    return data, np.array(labels, dtype=bool), tsne_mod, embed


#%% Periodicity
def get_psd(data, rate, win_size):

    ### Demo cells: 583 (strong periodicity) and 48 (low periodicity)
    pcf = pipe.load_pcf(r'W:\Neurophysiology-Storage1\Wahl\Hendrik\PhD\Data\Batch3\M41\20200625')

    neurons = [583, 49]
    rate = 1/5  # samples per centimeter

    fig, ax = plt.subplots(len(neurons), 3, sharex='col')
    for i, neuron in enumerate(neurons):
        data = pcf.bin_avg_activity[neuron]
        psd, freqs = psd_array_multitaper(data, rate, adaptive=True, normalization='full')

        # Plot activity
        ax[i, 0].plot(np.arange(0, 400, 5), data)
        ax[i, 0].set_ylabel(f'mean dF/F')

        # Plot frequencies
        ax[i, 1].plot(freqs, psd)
        ax[i, 1].set_ylabel(f'PSD')

        # Plot periods
        ax[i, 2].plot(1/freqs, psd)
        ax[i, 2].set_ylabel(f'PSD')


    ax[0, 0].set_title(f'Spatial activity map')
    ax[0, 1].set_title(f'Frequency power density')
    ax[0, 2].set_title(f'Period power density')
    ax[1, 0].set_xlabel(f'VR position [cm]')
    ax[1, 1].set_xlabel(f'Frequency [1/cm]')
    ax[1, 2].set_xlabel(f'Period [cm]')
    plt.tight_layout()




#%% Visualization

def plot_eigenvalues(evals, limit=True):
  """
  Plots eigenvalues.

  Args:
     (numpy array of floats) : Vector of eigenvalues

  Returns:
    Nothing.

  """

  plt.figure()
  plt.plot(np.arange(1, len(evals) + 1), evals, 'o-k')
  plt.xlabel('Component')
  plt.ylabel('Eigenvalue')
  plt.title('Scree plot')
  if limit:
    plt.show()


def plot_variance_explained(variance_explained, cutoff=0.95, cum=True, return_cutoff=True):
    """
    Plots eigenvalues.

    Args:
    variance_explained (numpy array of floats) : Vector of variance explained
                                                 for each PC

    Returns:
    Nothing.

    """

    x = np.arange(0, len(variance_explained)+1)
    if cum:
        y = np.cumsum(variance_explained) / np.sum(variance_explained)
    else:
        y = variance_explained

    plt.figure()
    plt.plot(x, np.insert(y, 0, 0), '--k', label=f'Cutoff at component {np.where(y>cutoff)[0][0]+1}')
    plt.axhline(cutoff, color='r')
    plt.ylim(-0.05, 1.05)
    plt.xlabel('Number of components')
    plt.ylabel('Variance explained')
    plt.legend()
    plt.show()
    if return_cutoff:
        return np.where(y > cutoff)[0][0]+1


def plot_weights(weights, n_comps, params, var_exp=None):

    weights_long = weights[:n_comps].flatten()
    labels = np.array([[x+1]*weights.shape[1] for x in range(n_comps)]).flatten()
    bins = np.tile(np.arange(weights.shape[1])*params['bin_length'], n_comps)
    df = pd.DataFrame({'weight':weights_long, 'VR position [cm]': bins, 'Component': labels})
    g = sns.FacetGrid(df, col='Component', col_wrap=4)
    g.map(sns.lineplot, 'VR position [cm]', 'weight')

    for idx, ax in enumerate(g.axes.ravel()):
        for zone in params['zone_borders']:
            ax.axvspan(zone[0]*params['bin_length'], zone[1]*params['bin_length'], color='red', alpha=0.1)
            ax.axhline(0, color='grey', linestyle='--', alpha=0.7)
        if var_exp is not None:
            ax.set_title(f'Component {idx+1} ({int(var_exp[idx]*1000)/10}%)')


def plot_pc_with_hist(scores, weights, labels, params, components=(0, 1)):
    """
    Plots overview of PCA results: Data points across two components (default first two), with histogram distributions
    of place cells and non-place cells, as well as the weight profile of the first two components (upper right).

    Args:
        scores (np.array): Shape (n_samples, n_features), values for each feature of every sample (from pca.transform())
        weights (np.array): Shape (n_features, n_features), weight distribution for all features (from pca.components_)
        labels (np.array): Shape (n_samples,), bool value whether a sample is a place cell
        params (dict): Parameter dict from pcf object (to plot reward zone positions)
        components (tuple): Indices of principal components the dataset should be plotted against (default (0, 1)
        fname (str): optional, if not None, figure is saved at the path defined by fname

    Returns:
        nothing
    """

    # Filter data for the two principal components
    x = scores[:, components[0]]
    y = scores[:, components[1]]

    weight_1 = weights[components[0]]
    weight_2 = weights[components[1]]

    # definitions for the axes
    left, width = 0.1, 0.65
    bottom, height = 0.1, 0.65
    right, top = 0.2, 0.2
    spacing = 0.005

    rect_scatter = [left, bottom, width, height]
    rect_histx = [left, bottom + height + spacing, width, top]
    rect_histy = [left + width + spacing, bottom, right, height]
    rect_weights = [left + width + spacing, bottom + height + spacing, right, top]

    # start with a rectangular Figure
    fig = plt.figure(figsize=(8, 8))

    ax_scatter = plt.axes(rect_scatter)
    ax_scatter.tick_params(direction='in', top=True, right=True)
    ax_histx = plt.axes(rect_histx)
    ax_histx.tick_params(direction='in', labelbottom=False, labelright=False)
    ax_histy = plt.axes(rect_histy)
    ax_histy.tick_params(direction='in', labelleft=False, labeltop=False)
    ax_weight = plt.axes(rect_weights)
    ax_weight.tick_params(direction='in', labelleft=False, labelbottom=False)

    # the scatter plot:
    colors = ['blue', 'orange']
    ax_scatter.scatter(x[~labels], y[~labels], label='no place cells', alpha=0.5, color=colors[0])
    ax_scatter.scatter(x[labels], y[labels], label='place cells', alpha=0.5, color=colors[1])
    ax_scatter.legend()
    ax_scatter.set_ylabel('Principal Component 2')
    ax_scatter.set_xlabel('Principal Component 1')

    # Get color of different groups
    # colors = [sc.to_rgba(i) for i in np.unique(labels)]

    # Plot histograms with the appropriate group color
    ax_histx.hist(x[~labels], bins=25, color=colors[0], alpha=0.7)
    ax_histy.hist(y[~labels], bins=25, color=colors[0], alpha=0.7, orientation='horizontal')
    ax_histx_2 = ax_histx.twinx()
    ax_histx_2.tick_params(direction='in', labelright=False)
    ax_histy_2 = ax_histy.twiny()
    ax_histy_2.tick_params(direction='in', labeltop=False)
    ax_histx_2.hist(x[labels], bins=25, color=colors[1], alpha=0.7)
    ax_histy_2.hist(y[labels], bins=25, color=colors[1], alpha=0.7, orientation='horizontal')

    ax_histx.set_xlim(ax_scatter.get_xlim())
    ax_histy.set_ylim(ax_scatter.get_ylim())

    # Plot weight profiles of the first two principal components
    ax_weight.plot(weight_1, label=f'PC {components[0]}')
    ax_weight.plot(weight_2, label=f'PC {components[1]}')
    for zone in params['zone_borders']:
        ax_weight.axvspan(zone[0], zone[1], color='red', alpha=0.1)
    ax_weight.axhline(0, color='grey', linestyle='--')

    plt.show()
    return fig


#%% PCA

def random():
    # Load data
    pcf = pipe.load_pcf(r'W:\Neurophysiology-Storage1\Wahl\Hendrik\PhD\Data\Batch3\M41\20200511')

    # Neurons as samples, position bins as features
    raw_data = pcf.bin_avg_activity
    pc_idx = [x[0] for x in pcf.place_cells]
    labels = np.zeros(len(raw_data))
    labels[pc_idx] = 1

    # Standardize (z-score) data
    data = raw_data-np.mean(raw_data, axis=0)/np.std(raw_data, axis=0)

    # perform PCA (input as shape (n_samples, n_features)
    score, evectors, evals = pca(data)

    # plot the eigenvalues
    plot_eigenvalues(evals, limit=False)

    # plot variance explained
    plot_variance_explained(np.cumsum(evals)/np.sum(evals), cutoff=0.95)

    # visualize weights of the n-th principal component
    n_comp = 1
    plt.figure()
    for i in range(n_comp):
        plt.plot(weights[i], label=f'Comp {i+1}', linewidth=2)
        for zone in pcf.params['zone_borders']:
            plt.axvspan(zone[0], zone[1], color='red', alpha=0.1)
    plt.legend()

    perform_PCA(data, labels, 2, plot=True)

    # built-in PCA
    pca_model = PCA(n_components=80)  # Initializes PCA
    out = pca_model.fit(data)  # Performs PCA
    scores = pca_model.transform(data)
    weights = pca_model.components_

    # Plot first three components
    df = pd.DataFrame(np.vstack((scores.T, labels)).T)
    df.rename(columns=str, inplace=True)
    df.rename(columns={'80': 'labels'}, inplace=True)
    pio.renderers.default = 'browser'
    fig = px.scatter_3d(df, x='0', y='1', z='2', color='labels')
    fig.show()

    def perform_PCA(data, labels, n_comp, plot=False):
        pca_model = PCA(n_components=80)  # Initializes PCA
        pca_model.fit(data)  # Performs PCA
        scores = pca_model.transform(data)
        nrows = 3
        ncols = 3
        if plot:
            fig, ax= plt.subplots(nrows, ncols)
            i = 0
            for row in range(nrows):
                for col in range(ncols):
                    ax[row, col].scatter(x=scores[:, i], y=scores[:, i+1], s=10, c=labels)
                    ax[row, col].set_xlabel(f'Component {i+1}')
                    ax[row, col].set_ylabel(f'Component {i+2}')
                    i += 1

    # Plot PCA component with overlaying histogram
    plot_pc_with_hist(-score, evectors, (0, 1), labels, pcf.params)


    # t-SNE
    fig, ax = plt.subplots(2, 3)
    perplexities = [5, 30, 50, 75, 100, 500]
    count = 0
    for row in range(2):
        for col in range(3):
            pca_mod = PCA(n_components=50)
            pca_results = pca_mod.fit_transform(data)
            tsne_mod = TSNE(n_components=2, perplexity=perplexities[count], n_iter=5000)
            embed = tsne_mod.fit_transform(pca_results)
            ax[row, col].scatter(x=embed[:, 0], y=embed[:, 1], c=labels)
            ax[row, col].set_xlabel('Component 1')
            ax[row, col].set_ylabel('Component 2')
            ax[row, col].set_title(f'Perplexity {perplexities[count]}')
            count += 1

    # 3D
    for perp in perplexities:
        tsne_mod = TSNE(n_components=3, perplexity=perp, n_iter=5000)
        embed = tsne_mod.fit_transform(data)
        df = pd.DataFrame(np.vstack((embed.T, labels)).T)
        df.rename(columns=str, inplace=True)
        df.rename(columns={'3': 'labels'}, inplace=True)
        pio.renderers.default = 'browser'
        fig = px.scatter_3d(df, x='0', y='1', z='2', color='labels')
        fig.show()







