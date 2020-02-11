"""T1 Linear - Clinica Pipeline.
This file has been generated automatically by the `clinica generate template`
command line tool. See here for more details: https://gitlab.icm-institute.org/aramislab/clinica/wikis/docs/InteractingWithClinica.
"""

# WARNING: Don't put any import statement here except if it's absolutly
# necessary. Put it *inside* the different methods.
# Otherwise it will slow down the dynamic loading of the pipelines list by the
# command line tool.
import clinica.pipelines.engine as cpe


class T1Linear(cpe.Pipeline):
    """T1 Linear SHORT DESCRIPTION.
    This preprocessing pipeline includes globally three steps:
    1) N4 bias correction (performed with ANTS).
    2) Linear registration to MNI (MNI icbm152 nlinear sym template)
      (performed with ANTS) - RegistrationSynQuick.
    3) Cropping the background (in order to save computational power).  4)
    Histogram-based intensity normalization. This is a custom function
    performed by the binary ImageMath included with ANTS.

    Warnings:
        - A WARNING.

    Args:
        bids_directory (str): Folder with BIDS structure.
        caps_directory (str): Folder where CAPS structure will be stored.
        ref_template (str): reference template used for image registration.
        working_directory (str): Folder containing a temporary space to save.
        intermediate results.
        tsv: The Subjects-Sessions list file (in .tsv format).

    Returns:
        A clinica pipeline object containing the T1 Linear pipeline.

    Raises:

    Example:
        >>> from t1_linear import T1Linear
        >>> pipeline = T1Linear('~/MYDATASET_BIDS', '~/MYDATASET_CAPS')
        >>> pipeline.parameters = {
        >>>     # ...
        >>> }
        >>> pipeline.base_dir = '/tmp/'
        >>> pipeline.run()
    """

    def check_custom_dependencies(self):
        """Check dependencies that can not be listed in the `info.json` file.
        """
        pass

    def get_input_fields(self):
        """Specify the list of possible inputs of this pipeline.

        Returns:
            A list of (string) input fields name.
        """

        return ['t1w']

    def get_output_fields(self):
        """Specify the list of possible outputs of this pipeline.

        Returns:
            A list of (string) output fields name.
        """

        return ['image_id']

    def build_input_node(self):
        """Build and connect an input node to the pipeline.
        """
        import os
        import sys
        import clinica
        import nipype.interfaces.utility as nutil
        import nipype.pipeline.engine as npe
        from clinica.utils.inputs import check_bids_folder
        from clinica.utils.participant import get_subject_session_list
        from clinica.utils.exceptions import ClinicaBIDSError, ClinicaException
        from clinica.utils.inputs import clinica_file_reader
        from clinica.utils.input_files import T1W_NII
        from clinica.utils.inputs import fetch_file
        from clinica.utils.stream import cprint

        check_bids_folder(self.bids_directory)
        is_bids_dir = True
        head_tail = os.path.split(clinica.__file__)
        path_to_mask = os.path.join(head_tail[0], 'resources', 'masks')
        self.ref_template = os.path.join(
                path_to_mask, 'mni_icbm152_t1_tal_nlin_sym_09c.nii')
        self.ref_crop = os.path.join(path_to_mask, 'ref_cropped_template.nii.gz')
        url1 = "https://aramislab.paris.inria.fr/files/data/img_t1_linear/ref_cropped_template.nii.gz"
        url2 = "https://aramislab.paris.inria.fr/files/data/img_t1_linear/mni_icbm152_t1_tal_nlin_sym_09c.nii"

        if not(os.path.exists(self.ref_template)):
            try:
                fetch_file(url2, self.ref_template)
            except IOError as err:
                cprint('Unable to download required template (mni_icbm152) for processing:', err)

        if not(os.path.exists(self.ref_crop)):
            try:
                fetch_file(url1, self.ref_crop)
            except IOError as err:
                cprint('Unable to download required template (ref_crop) for processing:', err)

        self.sessions, self.subjects = get_subject_session_list(
                self.bids_directory,
                self.tsv_file,
                is_bids_dir,
                False,
                self.base_dir
                )
        # Inputs from anat/ folder
        # ========================
        # T1w file:
        try:
            t1w_files = clinica_file_reader(
                    self.subjects,
                    self.sessions,
                    self.bids_directory,
                    T1W_NII)
        except ClinicaException as e:
            err = 'Clinica faced error(s) while trying to read files in your CAPS directory.\n' + str(e)
            raise ClinicaBIDSError(err)

        # Read tsv file and load inputs
        read_node = npe.Node(
                name="ReadingFiles",
                iterables=[
                    ('t1w', t1w_files),
                    ],
                synchronize=True,
                interface=nutil.IdentityInterface(
                    fields=self.get_input_fields())
                )
        self.connect([
            (read_node, self.input_node, [('t1w', 't1w')]),
            ])
        # This node is supposedly used to load BIDS inputs when this pipeline is
        # not already connected to the output of a previous Clinica pipeline.
        # For the purpose of the example, we simply read input arguments given
        # by the command line interface and transmitted here through the
        # `self.parameters` dictionary and pass it to the `self.input_node` to
        # further by used as input of the core nodes.

    def build_output_node(self):
        """Build and connect an output node to the pipeline.
        """
        # In the same idea as the input node, this output node is supposedly
        # used to write the output fields in a CAPS. It should be executed only
        # if this pipeline output is not already connected to a next Clinica
        # pipeline.
        from nipype.interfaces.io import DataSink
        import nipype.pipeline.engine as npe

        write_node = npe.Node(
                name="WriteCaps",
                interface=DataSink()
                )
        write_node.inputs.base_directory = self.caps_directory
        write_node.inputs.parameterization = False
        self.connect([
            (self.output_node, write_node, [('image_id', 'image_id')]),
            ])

    def build_core_nodes(self):
        """Build and connect the core nodes of the pipeline.
        """
        import nipype.interfaces.utility as nutil
        import nipype.pipeline.engine as npe
        from clinica.utils.filemanip import get_subject_id
        from clinica.utils.nipype import fix_join
        from nipype.interfaces import ants
        from .t1_linear_utils import (crop_nifti, container_from_filename, get_data_datasink)

        image_id_node = npe.Node(
                interface=nutil.Function(
                    input_names=['bids_or_caps_file'],
                    output_names=['image_id'],
                    function=get_subject_id),
                name='ImageID'
                )

        # The core (processing) nodes
        # =====================================

        # 1. N4biascorrection by ANTS. It uses nipype interface.
        n4biascorrection = npe.Node(
                name='n4biascorrection',
                interface=ants.N4BiasFieldCorrection(
                    dimension=3,
                    save_bias=True,
                    bspline_fitting_distance=600
                    )
                )

        # 2. `RegistrationSynQuick` by *ANTS*. It uses nipype interface.
        ants_registration_node = npe.Node(
                name='antsRegistrationSynQuick',
                interface=ants.RegistrationSynQuick()
                )
        ants_registration_node.inputs.fixed_image = self.ref_template
        ants_registration_node.inputs.transform_type = 'a'
        ants_registration_node.inputs.dimension = 3

        # 3. Crop image (using nifti). It uses custom interface, from utils file

        cropnifti = npe.Node(
                name='cropnifti',
                interface=nutil.Function(
                    function=crop_nifti,
                    input_names=['input_img', 'ref_crop'],
                    output_names=['output_img', 'crop_template']
                    )
                )
        cropnifti.inputs.ref_crop = self.ref_crop

        # Other nodes
        # =====================================
        # Get substitutions to rename files
        get_ids = npe.Node(
                interface=nutil.Function(
                    input_names=['image_id'],
                    output_names=['image_id_out', 'subst_ls'],
                    function=get_data_datasink),
                name="GetIDs")
        # Find container path from t1w filename
        container_path = npe.Node(
                nutil.Function(
                    input_names=['bids_or_caps_filename'],
                    output_names=['container'],
                    function=container_from_filename),
                name='ContainerPath')
        # Connection
        # ==========
        self.connect([
            (self.input_node, image_id_node, [('t1w', 'bids_or_caps_file')]),
            (self.input_node, container_path, [('t1w', 'bids_or_caps_filename')]),
            (image_id_node , ants_registration_node, [('image_id', 'output_prefix')]),
            (self.input_node, n4biascorrection, [("t1w", "input_image")]),

            (n4biascorrection, ants_registration_node, [('output_image', 'moving_image')]),

            (ants_registration_node, cropnifti, [('warped_image', 'input_img')]),

            # Connect to DataSink
            (container_path, self.output_node, [(('container', fix_join, 't1_linear'), 'container')]),
            (image_id_node, get_ids, [('image_id', 'image_id')]),
            (get_ids, self.output_node, [('image_id_out', 'image_id')]),
            (get_ids, self.output_node, [('subst_ls', 'substitutions')]),
            (n4biascorrection, self.output_node, [('output_image', 'outfile_corr')]),
            (ants_registration_node, self.output_node, [('warped_image', 'outfile_reg')]),
            (cropnifti, self.output_node, [('output_img', 'outfile_crop')]),
            ])
