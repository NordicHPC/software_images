BINSCRIPTS = hpcmodules.py  list_images.py  umount_all_images.py  umount_image.py create_software_image.py create_user_image.py filefs.py module_load mount_image.py cleanup_images.py get_dir_size.py
INSTDIR=/cluster/software_images/bin
SHELL:=/bin/bash
install:
	for p in $(BINSCRIPTS); do \
	    install -D $$p $(INSTDIR)/$$p; \
	    pysc=`echo $$p | sed -e 's/\.py$$//'`; \
	    if [[ $$p != $$pysc ]]; then \
		ln -fs $(INSTDIR)/$$p $(INSTDIR)/$$pysc; \
	    fi \
	done

.PHONY: install
